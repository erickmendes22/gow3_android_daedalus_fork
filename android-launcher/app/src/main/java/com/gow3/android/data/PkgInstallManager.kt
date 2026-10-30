package com.gow3.android.data

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Environment
import android.provider.DocumentsContract
import android.provider.Settings
import android.widget.Toast
import java.io.File
import java.io.FileInputStream
import java.io.IOException
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import ro.cobrabm.fexdroid.RuntimeInstaller
import ro.cobrabm.fexdroid.SotcPaths

/**
 * Direct, zero-copy PKG installation.
 *
 * Base game: select a PKG and an empty destination folder. Updates: select a
 * PKG and install directly into the already selected game folder after title validation.
 * orbis-pkg-util opens the original local file and creates the unpacked files
 * inside that folder. The PKG is never duplicated; there is no staging folder
 * and the output is never copied between folders.
 *
 * This native extractor currently requires a directly addressable filesystem
 * path for both the PKG and destination. A remote SAF/cloud provider cannot
 * work with its seek/mmap I/O; reject it instead of making an implicit copy.
 *
 * Legacy separately selected update folders remain usable through the launcher;
 * installing an update PKG now merges it into the selected game instead.
 */
internal class PkgInstallManager(
    private val activity: Activity,
    private val onState: (busy: Boolean, message: String?) -> Unit,
) {
    companion object {
        const val REQUEST_BASE_PKG = 1008
        const val REQUEST_UPDATE_PKG = 1009
        const val REQUEST_BASE_DIRECTORY = 1010
        const val REQUEST_UPDATE_DIRECTORY = 1011
        const val REQUEST_ALL_FILES_ACCESS = 1012
        const val REQUEST_STORAGE = 1014
        private val TITLE_PATTERN = Regex("^CUSA[0-9]{5}$", RegexOption.IGNORE_CASE)
    }

    private data class Selection(val pkg: Uri, val update: Boolean)
    private var selected: Selection? = null
    private var selectedDestination: Uri? = null
    private var pendingPermissionUpdate: Boolean? = null
    private val installing = AtomicBoolean(false)
    private val worker = Executors.newSingleThreadExecutor()
    private val preferences get() = activity.getSharedPreferences(SotcPaths.prefsName(activity), Activity.MODE_PRIVATE)

    private fun localized(en: String, pt: String): String =
        if (LanguageManager.read(activity) == LanguageManager.PT) pt else en

    fun pickBasePkg() = pick(false)
    fun pickUpdatePkg() = pick(true)

    private fun pick(update: Boolean) {
        if (installing.get() || selected != null || pendingPermissionUpdate != null) {
            Toast.makeText(activity, localized("Finish the current selection before installing another PKG", "Finalize a seleção anterior antes de instalar outro PKG"),
                Toast.LENGTH_SHORT).show()
            return
        }
        if (update) {
            val base = preferences.getString("game_dir", null)?.let(::File)
            if (base == null || !File(base, "eboot.bin").isFile) {
                error(localized("Select or install the base game before the update", "Selecione ou instale o jogo base antes do update"))
                return
            }
        }
        // targetSdk 28 uses the legacy read/write permission dialog, including
        // on Android 11+. SAF selection alone does not authorize native path I/O.
        if (activity.applicationInfo.targetSdkVersion < 30 &&
            (activity.checkSelfPermission(Manifest.permission.READ_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED ||
             activity.checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED)) {
            pendingPermissionUpdate = update
            activity.requestPermissions(arrayOf(Manifest.permission.READ_EXTERNAL_STORAGE,
                Manifest.permission.WRITE_EXTERNAL_STORAGE), REQUEST_STORAGE)
            return
        }
        activity.startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "*/*"
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }, if (update) REQUEST_UPDATE_PKG else REQUEST_BASE_PKG)
    }

    fun onPermissionResult(request: Int, grantResults: IntArray) {
        if (request != REQUEST_STORAGE) return
        val update = pendingPermissionUpdate ?: return
        pendingPermissionUpdate = null
        if (grantResults.isNotEmpty() && grantResults.all { it == PackageManager.PERMISSION_GRANTED }) {
            pick(update)
        } else {
            error(localized("Storage permission was not granted. Installation has not started.", "Permissão de armazenamento não concedida. A instalação não foi iniciada."))
        }
    }

    fun onPickerResult(request: Int, result: Int, data: Intent?): Boolean {
        when (request) {
            REQUEST_BASE_PKG, REQUEST_UPDATE_PKG -> {
                if (result != Activity.RESULT_OK || data?.data == null) return true
                val update = request == REQUEST_UPDATE_PKG
                selected = Selection(data.data!!, update)
                if (update) {
                    val base = preferences.getString("game_dir", null)?.let(::File)
                    if (base == null || !File(base, "eboot.bin").isFile) {
                        clearSelection()
                        error(localized("Select or install the base game before the update", "Selecione ou instale o jogo base antes do update"))
                        return true
                    }
                    // Internal URI only: updates use the selected game folder.
                    selectedDestination = Uri.fromFile(base)
                    startSelectedInstall()
                    return true
                }
                try {
                    activity.startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).apply {
                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or
                            Intent.FLAG_GRANT_WRITE_URI_PERMISSION or
                            Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
                    }, if (update) REQUEST_UPDATE_DIRECTORY else REQUEST_BASE_DIRECTORY)
                } catch (e: Exception) {
                    selected = null
                    error(localized("Could not open the folder picker: ${e.message}", "Não foi possível abrir o seletor de pastas: ${e.message}"))
                }
                return true
            }
            REQUEST_BASE_DIRECTORY, REQUEST_UPDATE_DIRECTORY -> {
                val choice = selected
                if (result != Activity.RESULT_OK || data?.data == null ||
                    choice == null ||
                    (request == REQUEST_UPDATE_DIRECTORY) != choice.update) {
                    selected = null
                    selectedDestination = null
                    return true
                }
                selectedDestination = data.data
                try {
                    activity.contentResolver.takePersistableUriPermission(
                        data.data!!, Intent.FLAG_GRANT_READ_URI_PERMISSION or
                            Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
                } catch (_: SecurityException) {
                    // The selection may be a non-persistable provider; we still
                    // validate real write access before extracting anything.
                }
                if (needsAllFilesAccess()) {
                    AlertDialog.Builder(activity)
                        .setTitle(localized("Direct installation permission", "Permissão para instalação direta"))
                        .setMessage(localized("To extract the PKG directly into the selected folder, ", "Para extrair o PKG diretamente na pasta escolhida, ") +
                            localized("the extractor needs direct access to ", "o extrator precisa acessar os arquivos ") +
                            localized("local files. Allow access to ", "locais pelo caminho de armazenamento. Autorize o acesso a ") +
                            localized("all files to continue.", "todos os arquivos para continuar."))
                        .setPositiveButton(localized("Allow", "Permitir")) { _, _ ->
                            try {
                                activity.startActivityForResult(Intent(
                                    Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                                    Uri.parse("package:${activity.packageName}")),
                                    REQUEST_ALL_FILES_ACCESS)
                            } catch (e: Exception) {
                                clearSelection()
                                error(localized("Could not request file access: ${e.message}", "Não foi possível solicitar acesso aos arquivos: ${e.message}"))
                            }
                        }
                        .setNegativeButton(localized("Cancel", "Cancelar")) { _, _ -> clearSelection() }
                        .show()
                } else {
                    startSelectedInstall()
                }
                return true
            }
            REQUEST_ALL_FILES_ACCESS -> {
                if (needsAllFilesAccess()) {
                    clearSelection()
                    error(localized("Storage permission denied: installation cancelled", "Permissão de armazenamento negada: instalação cancelada"))
                } else {
                    startSelectedInstall()
                }
                return true
            }
            else -> return false
        }
    }

    private fun needsAllFilesAccess() =
        android.os.Build.VERSION.SDK_INT >= 30 &&
            activity.applicationInfo.targetSdkVersion >= 30 && !Environment.isExternalStorageManager()

    private fun clearSelection() {
        selected = null
        selectedDestination = null
    }

    private fun startSelectedInstall() {
        val choice = selected ?: return
        val destination = selectedDestination ?: return
        if (!installing.compareAndSet(false, true)) return
        clearSelection()
        onState(true, localized("Extracting PKG directly into the selected folder…", "Extraindo PKG diretamente na pasta selecionada…"))
        val dialog = AlertDialog.Builder(activity)
            .setTitle(if (choice.update) localized("Installing update PKG", "Instalando atualização PKG") else localized("Installing game PKG", "Instalando jogo PKG"))
            .setMessage(localized("Extraction uses the selected folder.", "A extração usa a pasta escolhida."))
            .setCancelable(false)
            .create()
        dialog.show()
        worker.execute {
            val result = runCatching {
                // PKG setup is available before GameActivity has ever run.
                // Install/validate the signed runtime first, on this worker.
                RuntimeInstaller.ensure(activity, activity.filesDir) { _ ->
                    activity.runOnUiThread {
                        val preparing = localized("Preparing game runtime…", "Preparando runtime do jogo…")
                        dialog.setMessage(preparing)
                        onState(true, preparing)
                    }
                }
                activity.runOnUiThread {
                    val extracting = localized("Extracting PKG directly into the selected folder…", "Extraindo PKG diretamente na pasta selecionada…")
                    dialog.setMessage(extracting)
                    onState(true, extracting)
                }
                install(choice.pkg, destination, choice.update)
            }
            activity.runOnUiThread {
                installing.set(false)
                dialog.dismiss()
                val message = result.fold(
                    onSuccess = { it },
                    onFailure = { localized("PKG not installed: ${it.message ?: it.javaClass.simpleName}", "PKG não instalado: ${it.message ?: it.javaClass.simpleName}") },
                )
                onState(false, message)
                AlertDialog.Builder(activity)
                    .setTitle(if (result.isSuccess) localized("PKG installed", "PKG instalado") else localized("PKG installation incomplete", "Instalação PKG não concluída"))
                    .setMessage(message)
                    .setPositiveButton("OK", null)
                    .show()
            }
        }
    }

    private fun install(sourceUri: Uri, targetUri: Uri, update: Boolean): String {
        val helper = File(activity.filesDir, "${SotcPaths.baseName(activity)}/arm64/bin/orbis-pkg-util")
        val bionic = (File(activity.filesDir,"${SotcPaths.baseName(activity)}/run-bionic.sh").isFile || File(activity.filesDir,"sotcport/run-sotc-bionic.sh").isFile)
        val loader = if (bionic) File("/system/bin/linker64") else File(activity.filesDir,
            "rootfs/usr/lib/aarch64-linux-gnu/ld-linux-aarch64.so.1")
        if (!helper.isFile || !helper.canExecute() || !loader.isFile)
            throw IOException(localized("The runtime does not contain the ARM64 PKG extractor", "O runtime não contém o extrator PKG ARM64"))

        // Resolve local primary/removable-storage document IDs. Never use
        // OpenInputStream -> temporary PKG; the extractor needs random access.
        val pkg = localDocumentFile(sourceUri, directory = false)
            ?: throw IOException(localized("The PKG must be on accessible local storage. ", "O PKG precisa estar num armazenamento local acessível. ") +
                localized("Remote or cloud files cannot be extracted directly without copying them.", "Não é possível extrair diretamente um arquivo remoto/cloud sem duplicá-lo."))
        val dest = localDocumentFile(targetUri, directory = true)
            ?: throw IOException(localized("The destination is not an accessible local folder", "Pasta de destino não é um diretório local acessível"))
        if (!pkg.isFile || !pkg.canRead())
            throw IOException(localized("Original PKG unavailable: ${pkg.path}", "PKG original indisponível: ${pkg.path}"))
        if (!dest.isDirectory || !dest.canWrite())
            throw IOException(localized("No write access to the selected folder: ${dest.path}", "Sem permissão de escrita na pasta escolhida: ${dest.path}"))
        if (!update && (pkg.canonicalFile == dest.canonicalFile || pkg.canonicalFile.parentFile == dest.canonicalFile))
            throw IOException(localized("Choose another folder: the PKG cannot be inside the destination", "Escolha outra pasta: o PKG não pode ficar dentro do destino"))
        val existingEntries = dest.listFiles()
            ?: throw IOException(localized("Could not list the selected folder", "Não foi possível listar a pasta escolhida"))
        val base = preferences.getString("game_dir", null)?.let(::File)
        val replacingUpdate = update && base?.canonicalFile == dest.canonicalFile
        if (update && !replacingUpdate)
            throw IOException(localized("The update destination must be the selected game folder", "O destino da atualização deve ser a pasta do jogo selecionado"))
        if (existingEntries.isNotEmpty() && !update)
            throw IOException(localized("Choose an empty folder for the base game", "Escolha uma pasta vazia para o jogo base"))
        if (!update && base != null && (base.canonicalFile == dest.canonicalFile ||
                isNested(dest.canonicalFile, base.canonicalFile)))
            throw IOException(localized("Do not extract an update inside the base game folder", "Não extraia uma atualização dentro da pasta do jogo base"))
        val updateDir = preferences.getString("update_dir", null)?.let(::File)
        if (!update && updateDir != null && updateDir.canonicalFile == dest.canonicalFile)
            throw IOException(localized("The selected folder is registered as an update", "A pasta escolhida está registrada como atualização"))

        FileInputStream(pkg).use { stream ->
            val magic = ByteArray(4)
            if (stream.read(magic) != 4 ||
                !magic.contentEquals(byteArrayOf(0x7f, 0x43, 0x4e, 0x54)))
                throw IOException(localized("The file does not have a PS4 PKG signature", "Arquivo não possui assinatura PKG PS4"))
        }
        val metadata = execute(loader, helper, listOf("info", pkg.canonicalPath), dest)
        val title = Regex("(?im)^\\s*Title ID:\\s*(CUSA[0-9]{5})\\s*$")
            .find(metadata)?.groupValues?.get(1)?.uppercase()
            ?: throw IOException(localized("TITLE_ID missing from the PKG header", "TITLE_ID ausente no cabeçalho PKG"))
        if (!TITLE_PATTERN.matches(title)) throw IOException(localized("Invalid TITLE_ID", "TITLE_ID inválido"))
        if (!update && base != null && File(base, "eboot.bin").isFile &&
            ParamSfoTitle.readTitleId(File(base, "sce_sys/param.sfo")) == title)
            throw IOException(localized("Game ${title} is already installed in ${base.path}; ", "O jogo ${title} já está instalado em ${base.path}; ") +
                localized("select that game folder.", "selecione essa pasta do jogo."))
        if (update) {
            if (base == null || !File(base, "eboot.bin").isFile)
                throw IOException(localized("Select or install the base game before the update", "Selecione ou instale o jogo base antes do update"))
            val baseTitle = ParamSfoTitle.readTitleId(File(base, "sce_sys/param.sfo"))
                ?: throw IOException(localized("Base game TITLE_ID unavailable", "TITLE_ID do jogo base indisponível"))
            if (baseTitle != title)
                throw IOException(localized("Update ${title} does not match game ${baseTitle}", "Atualização ${title} não corresponde ao jogo ${baseTitle}"))
        }

        // After title validation, update files replace their counterparts in
        // the selected game folder. The base files absent from the PKG remain.
        try {
            val arguments = mutableListOf("extract", pkg.canonicalPath,
                "--output", dest.canonicalPath, "--quiet")
            if (replacingUpdate) arguments.add("--force")
            execute(loader, helper, arguments, dest)
            val extractedTitle = ParamSfoTitle.readTitleId(File(dest, "sce_sys/param.sfo"))
                ?: throw IOException(localized("Incomplete extraction: invalid sce_sys/param.sfo", "Extração incompleta: sce_sys/param.sfo inválido"))
            if (extractedTitle != title || !File(dest, "eboot.bin").isFile)
                throw IOException(localized("Extracted content does not match the PKG or is incomplete", "Conteúdo extraído não corresponde ao PKG ou está incompleto"))
        } catch (failure: Exception) {
            // Roll back outputs only when the user explicitly selected an empty
            // directory. Never delete a previously installed update on failure:
            // in-place replacement cannot be transactional without extra storage.
            if (!replacingUpdate)
                dest.listFiles()?.forEach { created -> created.deleteRecursively() }
            throw failure
        }
        val edit = preferences.edit().putString("game_dir", dest.canonicalPath)
        // The game now contains the update. Do not overlay an older separate
        // update on top of it on the next launch; keep those files untouched.
        if (update) edit.remove("update_dir")
        if (!edit.commit())
            throw IOException(localized("Content extracted, but the folder could not be selected", "Conteúdo extraído, mas não foi possível selecionar a pasta"))
        return if (update)
            localized("Update ${title} installed directly into ${dest.path}.", "Update ${title} instalado diretamente em ${dest.path}.")
        else localized("Game ${title} installed directly into ${dest.path}.", "Jogo ${title} instalado diretamente em ${dest.path}.")
    }

    private fun isNested(dir: File, ancestor: File): Boolean {
        var current: File? = dir
        while (current != null) {
            if (current == ancestor) return true
            current = current.parentFile
        }
        return false
    }

    /**
     * SAF grants do not translate into Linux pathname permissions. We only
     * resolve actual local storage volumes, then check File.canRead/Write.
     * SAF destinations backed by cloud/virtual providers are not supported
     * by the current native pathname-only PKG extractor.
     */
    private fun localDocumentFile(uri: Uri, directory: Boolean): File? {
        return try {
            if (directory && uri.scheme == "file") {
                // Only the internally generated selected-game destination uses file://.
                val selectedGame = preferences.getString("game_dir", null)?.let(::File)?.canonicalFile
                val candidate = uri.path?.let(::File)?.canonicalFile
                return if (candidate != null && candidate == selectedGame) candidate else null
            }
            val authority = uri.authority
            val result = if (authority == "com.android.externalstorage.documents") {
                val id = if (directory) DocumentsContract.getTreeDocumentId(uri)
                    else DocumentsContract.getDocumentId(uri)
                val colon = id.indexOf(':')
                if (colon <= 0) return null
                val volume = id.substring(0, colon)
                val relative = id.substring(colon + 1)
                val root = if (volume.equals("primary", ignoreCase = true)) {
                    Environment.getExternalStorageDirectory()
                } else {
                    if (!Regex("[A-Za-z0-9_-]{4,24}").matches(volume)) return null
                    File("/storage", volume)
                }
                val output = File(root, relative).canonicalFile
                if (!isNested(output, root.canonicalFile)) return null
                output
            } else {
                // Downloads/media may return their own document providers for
                // local PKGs. Resolve the real path only when the provider
                // exposes it; never stream/copy a remote file to a temp PKG.
                if (directory) return null
                val id = runCatching { DocumentsContract.getDocumentId(uri) }.getOrNull()
                val raw = if (id?.startsWith("raw:") == true) id.removePrefix("raw:")
                    else activity.contentResolver.query(uri,
                        arrayOf(android.provider.MediaStore.MediaColumns.DATA),
                        null, null, null)?.use { cursor ->
                        if (cursor.moveToFirst() && !cursor.isNull(0))
                            cursor.getString(0) else null
                    }
                if (raw.isNullOrBlank()) return null
                File(raw).canonicalFile
            }
            // Reject arbitrary providers that point at app-private paths or
            // any path outside mounted external storage volumes.
            val primary = Environment.getExternalStorageDirectory().canonicalFile
            val storage = File("/storage").canonicalFile
            if (!isNested(result, primary) && !isNested(result, storage)) return null
            result
        } catch (_: Exception) {
            null
        }
    }

    private fun execute(loader: File, executable: File, args: List<String>,
                        workingDir: File): String {
        val prefix = if ((File(activity.filesDir,"${SotcPaths.baseName(activity)}/run-bionic.sh").isFile || File(activity.filesDir,"sotcport/run-sotc-bionic.sh").isFile))
            listOf(executable.absolutePath) else listOf(loader.absolutePath, executable.absolutePath)
        val builder = ProcessBuilder(prefix + args)
            .directory(workingDir)
            .redirectErrorStream(true)
        val files = activity.filesDir
        builder.environment()["LD_LIBRARY_PATH"] =
            File(files, "${SotcPaths.baseName(activity)}/arm64/lib").path + ":" +
            File(files, "rootfs/usr/lib/aarch64-linux-gnu").path + ":" +
            File(files, "rootfs/usr/lib").path
        val process = builder.start()
        val output = StringBuilder()
        process.inputStream.bufferedReader().useLines { lines ->
            lines.forEach { line ->
                if (output.length < 24_000) output.appendLine(line)
            }
        }
        val status = process.waitFor()
        if (status != 0)
            throw IOException(localized("Extraction failed (${status}): ", "Extração falhou (${status}): ") + output.takeLast(1600))
        return output.toString()
    }
}

/** Reads the TITLE_ID directly from the PS4 PARAM.SFO key and data tables. */
internal object ParamSfoTitle {
    fun readTitleId(file: File): String? = runCatching {
        if (!file.isFile || file.length() < 20 || file.length() > 8L * 1024 * 1024)
            return null
        val bytes = file.readBytes()
        val b = java.nio.ByteBuffer.wrap(bytes).order(java.nio.ByteOrder.LITTLE_ENDIAN)
        if (b.int != 0x46535000) return null
        b.int
        val keys = b.int
        val data = b.int
        val count = b.int
        if (keys < 20 || data < keys || data > bytes.size || count !in 1..1024)
            return null
        for (i in 0 until count) {
            val entry = 20 + i * 16
            if (entry + 16 > bytes.size) return null
            val name = keys + (b.getShort(entry).toInt() and 0xffff)
            val len = b.getInt(entry + 4)
            val offset = data + b.getInt(entry + 12)
            if (name !in keys until data || len < 0 || offset < data ||
                offset.toLong() + len > bytes.size.toLong()) continue
            val nameEnd = (name until data).firstOrNull { bytes[it] == 0.toByte() } ?: continue
            if (String(bytes, name, nameEnd - name, Charsets.UTF_8) == "TITLE_ID") {
                val id = String(bytes, offset, len, Charsets.UTF_8).trimEnd('\u0000')
                if (Regex("CUSA[0-9]{5}").matches(id)) return id.uppercase()
            }
        }
        null
    }.getOrNull()
}
