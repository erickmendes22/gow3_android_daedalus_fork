package ro.cobrabm.fexdroid;

import android.content.Context;
import android.net.Uri;
import java.io.*;
import java.nio.file.Files;
import java.util.*;
import java.util.zip.*;

/** Back up the HLE SaveData tree, not game PKGs or caches. Stop the game before use. */
final class Order1886SaveManager {
    private static final int BUFFER = 65536;
    private static final int MAX_FILES = 20000;
    private static final long MAX_BYTES = 2L * 1024 * 1024 * 1024;
    private final Context context;
    private final File root;

    Order1886SaveManager(Context context, File appBase) {
        this.context = context;
        this.root = new File(new File(appBase, "user"), "savedata");
    }

    private static void requireInside(File path, File base) throws IOException {
        String parent = base.getCanonicalPath() + File.separator;
        if (!path.getCanonicalPath().startsWith(parent))
            throw new IOException("Caminho de save fora do diretorio permitido");
    }

    private static long zipTree(File dir, File root, ZipOutputStream zip, long total,
                                int[] fileCount) throws IOException {
        File[] children = dir.listFiles();
        if (children == null) throw new IOException("Nao foi possivel listar saves: " + dir);
        Arrays.sort(children, Comparator.comparing(File::getName));
        for (File f : children) {
            requireInside(f, root);
            if (Files.isSymbolicLink(f.toPath()))
                throw new IOException("Link simbolico inesperado em saves");
            if (f.isDirectory()) {
                total = zipTree(f, root, zip, total, fileCount);
            } else if (f.isFile()) {
                if (++fileCount[0] > MAX_FILES || f.length() > MAX_BYTES - total)
                    throw new IOException("Limite de backup de saves excedido");
                String relative = root.toPath().relativize(f.toPath()).toString().replace('\\', '/');
                if (relative.isEmpty()) throw new IOException("Nome de save invalido");
                zip.putNextEntry(new ZipEntry("savedata/" + relative));
                try (InputStream in = new BufferedInputStream(new FileInputStream(f))) {
                    byte[] bytes = new byte[BUFFER]; int n;
                    while ((n = in.read(bytes)) >= 0) if (n > 0) zip.write(bytes, 0, n);
                }
                zip.closeEntry();
                total += f.length();
            }
        }
        return total;
    }

    void exportTo(Uri destination) throws IOException {
        if (!root.isDirectory()) throw new IOException("Ainda nao existem saves para exportar");
        try (OutputStream stream = context.getContentResolver().openOutputStream(destination, "wt")) {
            if (stream == null) throw new IOException("Destino de backup indisponivel");
            try (ZipOutputStream zip = new ZipOutputStream(new BufferedOutputStream(stream))) {
                int[] count = {0};
                zipTree(root, root, zip, 0, count);
                if (count[0] == 0) throw new IOException("Pasta de saves vazia");
            }
        }
    }

    private static void deleteTree(File f) throws IOException {
        if (!f.exists()) return;
        File[] children = f.listFiles();
        if (children != null) for (File child : children) deleteTree(child);
        if (!f.delete()) throw new IOException("Falha ao limpar temporario de save");
    }

    private static void merge(File src, File target, File tempRoot) throws IOException {
        File[] entries = src.listFiles();
        if (entries == null) throw new IOException("Saves importados invalidos");
        for (File entry : entries) {
            if (Files.isSymbolicLink(entry.toPath())) throw new IOException("Link de save invalido");
            File dest = new File(target, entry.getName());
            requireInside(dest, tempRoot);
            if (entry.isDirectory()) {
                if (dest.exists() && !dest.isDirectory())
                    throw new IOException("Conflito entre pasta e arquivo de save");
                if (!dest.isDirectory() && !dest.mkdirs())
                    throw new IOException("Nao foi possivel criar pasta de save");
                merge(entry, dest, tempRoot);
            } else if (entry.isFile()) {
                if (dest.isDirectory()) throw new IOException("Conflito de nome de save");
                File tmp = new File(dest.getParentFile(), dest.getName() + ".order-import-tmp");
                requireInside(tmp, tempRoot);
                if (tmp.exists() && !tmp.delete()) throw new IOException("Save temporario ocupado");
                try (InputStream in = new BufferedInputStream(new FileInputStream(entry));
                     OutputStream out = new BufferedOutputStream(new FileOutputStream(tmp))) {
                    byte[] data = new byte[BUFFER]; int n;
                    while ((n = in.read(data)) != -1) out.write(data, 0, n);
                }
                // Preserve the previous save if the final rename fails.
                File previous = new File(dest.getParentFile(), dest.getName() + ".order-previous");
                requireInside(previous, tempRoot);
                if (previous.exists()) throw new IOException("Backup temporario anterior bloqueia importacao");
                if (dest.exists() && !dest.renameTo(previous))
                    throw new IOException("Nao foi possivel preservar save anterior");
                if (!tmp.renameTo(dest)) {
                    if (previous.exists() && !previous.renameTo(dest))
                        throw new IOException("Falha ao ativar e restaurar save anterior");
                    throw new IOException("Nao foi possivel ativar save importado");
                }
                if (previous.exists() && !previous.delete())
                    throw new IOException("Save importado mas backup anterior nao foi removido");
            }
        }
    }

    void importFrom(Uri source) throws IOException {
        File staging = new File(new File(root.getParentFile(), ".save-import"),
                                "session-" + Long.toHexString(System.nanoTime()));
        File payload = new File(staging, "savedata");
        if (!payload.mkdirs()) throw new IOException("Nao foi possivel preparar importacao");
        int count = 0; long total = 0;
        try {
            try (InputStream in = context.getContentResolver().openInputStream(source)) {
                if (in == null) throw new IOException("ZIP de saves inacessivel");
                try (ZipInputStream zip = new ZipInputStream(new BufferedInputStream(in))) {
                    ZipEntry entry;
                    byte[] buffer = new byte[BUFFER];
                    while ((entry = zip.getNextEntry()) != null) {
                        String name = entry.getName().replace('\\', '/');
                        if (!name.startsWith("savedata/") || name.contains("//"))
                            throw new IOException("ZIP nao contem apenas savedata/");
                        File outFile = new File(staging, name);
                        requireInside(outFile, staging);
                        if (entry.isDirectory()) {
                            if (!outFile.isDirectory() && !outFile.mkdirs())
                                throw new IOException("Pasta de save invalida");
                        } else {
                            if (++count > MAX_FILES) throw new IOException("ZIP contem arquivos demais");
                            File parent = outFile.getParentFile();
                            if (!parent.isDirectory() && !parent.mkdirs())
                                throw new IOException("Pasta de save indisponivel");
                            try (OutputStream out = new BufferedOutputStream(new FileOutputStream(outFile))) {
                                int n;
                                while ((n = zip.read(buffer)) != -1) {
                                    total += n;
                                    if (total > MAX_BYTES) throw new IOException("ZIP de save muito grande");
                                    out.write(buffer, 0, n);
                                }
                            }
                        }
                        zip.closeEntry();
                    }
                }
            }
            if (count == 0) throw new IOException("ZIP nao contem saves");
            if (!root.isDirectory() && !root.mkdirs())
                throw new IOException("Nao foi possivel abrir pasta de saves");
            merge(payload, root, root.getParentFile());
        } finally {
            deleteTree(staging);
        }
    }
}
