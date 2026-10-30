package com.gow3.android

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.app.AlertDialog
import android.content.res.Configuration
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.core.view.WindowCompat
import com.gow3.android.data.GameFolderManager
import com.gow3.android.data.LanguageManager
import com.gow3.android.data.LogManager
import com.gow3.android.data.SaveManager
import com.gow3.android.data.PkgInstallManager
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import com.gow3.android.ui.LauncherScreen
import com.gow3.android.ui.components.LauncherColors
import com.gow3.android.ui.theme.Gow3LauncherTheme

class MainActivity : ComponentActivity() {
    companion object {
        private const val REQUEST_INITIAL_STORAGE = 1015
    }
    private lateinit var gameFolderManager: GameFolderManager
    private lateinit var saveManager: SaveManager
    private lateinit var logManager: LogManager
    private lateinit var pkgInstallManager: PkgInstallManager
    private val pkgBusy = mutableStateOf(false)
    private val pkgMessage = mutableStateOf<String?>(null)
    private val pkgGeneration = mutableIntStateOf(0)

    override fun attachBaseContext(newBase: Context) {
        super.attachBaseContext(applyLanguage(newBase))
    }

    /** 按 LanguageManager 的语言覆盖（或系统语言）为 MainActivity 注入 Locale 配置。 */
    private fun applyLanguage(base: Context): Context {
        val config = Configuration(base.resources.configuration)
        config.setLocale(LanguageManager.resolve(base))
        return base.createConfigurationContext(config)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, true)
        window.statusBarColor = LauncherColors.backgroundTop.toArgbCompat()
        window.navigationBarColor = LauncherColors.backgroundBottom.toArgbCompat()
        window.decorView.systemUiVisibility = 0

        gameFolderManager = GameFolderManager(this)
        saveManager = SaveManager(this)
        logManager = LogManager(this)
        pkgInstallManager = PkgInstallManager(this) { busy, message ->
            pkgBusy.value = busy
            pkgMessage.value = message
            if (!busy) pkgGeneration.intValue += 1
        }
        setContent {
            Gow3LauncherTheme(dynamicColor = false) {
                LauncherScreen(
                    onStartGame = {
                        if (!hasStoragePermission()) {
                            ensureInitialStorage()
                        } else if (gameFolderManager.hasGameFolder()) {
                            startActivity(Intent(this, ro.cobrabm.fexdroid.GameActivity::class.java))
                        }
                    },
                    onChooseGameFolder = { gameFolderManager.chooseGameFolder() },
                    onChooseUpdateFolder = { gameFolderManager.chooseUpdateFolder() },
                    onInstallBasePkg = { pkgInstallManager.pickBasePkg() },
                    onInstallUpdatePkg = { pkgInstallManager.pickUpdatePkg() },
                    pkgInstallBusy = pkgBusy.value,
                    pkgInstallMessage = pkgMessage.value,
                    pkgGeneration = pkgGeneration.intValue,
                    saves = saveManager,
                    logs = logManager,
                    onChangeLanguage = { value ->
                        LanguageManager.set(this, value)
                        recreate()
                    },
                )
            }
        }
        // User opt-in: skip the launcher only when a previously selected game
        // and storage permission are valid. Never loop on returning from the game.
        if (savedInstanceState == null &&
            getSharedPreferences("gow3", MODE_PRIVATE).getBoolean("launch_direct_game", false)) {
            window.decorView.post {
                if (!isFinishing && !isDestroyed && hasStoragePermission() &&
                    gameFolderManager.hasGameFolder() && !pkgBusy.value) {
                    startActivity(Intent(this, ro.cobrabm.fexdroid.GameActivity::class.java))
                }
            }
        }

        // The original targetSdk 28 storage permission must come FIRST, before
        // offering PKG installation or folder selection. A settings all-files
        // grant must not replace this runtime permission flow.
        if (savedInstanceState == null || !hasStoragePermission()) {
            window.decorView.post {
                if (!isFinishing && !isDestroyed) {
                    ensureInitialStorage()
                }
            }
        }
    }

    private fun hasStoragePermission(): Boolean =
        checkSelfPermission(Manifest.permission.READ_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED &&
            checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED

    private fun ensureInitialStorage() {
        if (!hasStoragePermission()) {
            requestPermissions(arrayOf(Manifest.permission.READ_EXTERNAL_STORAGE,
                Manifest.permission.WRITE_EXTERNAL_STORAGE), REQUEST_INITIAL_STORAGE)
            return
        }
        if (!gameFolderManager.hasGameFolder()) showFirstRunGameSource()
    }

    private fun showFirstRunGameSource() {
        AlertDialog.Builder(this)
            .setTitle(getString(R.string.setup_title))
            .setMessage(getString(R.string.setup_message))
            .setPositiveButton(getString(R.string.pkg_install)) { _, _ -> pkgInstallManager.pickBasePkg() }
            .setNegativeButton(getString(R.string.setup_folder)) { _, _ -> gameFolderManager.chooseGameFolder() }
            .setCancelable(false)
            .show()
    }

    @Deprecated("Legacy Activity Result API is required by this target SDK flow")
    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_INITIAL_STORAGE) {
            if (hasStoragePermission()) {
                ensureInitialStorage()
            } else {
                AlertDialog.Builder(this)
                    .setTitle(getString(R.string.storage_permission_title))
                    .setMessage(getString(R.string.storage_permission_message))
                    .setPositiveButton(getString(R.string.choose_again)) { _, _ -> ensureInitialStorage() }
                    .setNegativeButton(getString(R.string.dialog_ok), null)
                    .show()
            }
            return
        }
        gameFolderManager.onPermissionResult(requestCode, grantResults)
        pkgInstallManager.onPermissionResult(requestCode, grantResults)
    }

    @Deprecated("Legacy Activity Result API is required by this target SDK flow")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (saveManager.onActivityResult(requestCode, resultCode, data)) return
        if (logManager.onActivityResult(requestCode, resultCode, data)) return
        if (pkgInstallManager.onPickerResult(requestCode, resultCode, data)) return
        gameFolderManager.onFolderResult(requestCode, resultCode, data)
    }
}

private fun androidx.compose.ui.graphics.Color.toArgbCompat(): Int =
    android.graphics.Color.argb(
        (alpha * 255).toInt(),
        (red * 255).toInt(),
        (green * 255).toInt(),
        (blue * 255).toInt(),
    )
