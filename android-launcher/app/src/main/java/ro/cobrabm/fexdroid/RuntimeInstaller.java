package ro.cobrabm.fexdroid;

import android.content.Context;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.security.MessageDigest;
import java.util.function.Consumer;

/** Installs the signed APK's Linux runtime transactionally in this app's private data directory. */
public final class RuntimeInstaller {
    private static final String LOADER = "rootfs/usr/lib/aarch64-linux-gnu/ld-linux-aarch64.so.1";

    private static void deleteTree(File root) throws Exception {
        if (!root.exists()) return;
        Files.walkFileTree(root.toPath(), new SimpleFileVisitor<java.nio.file.Path>() {
            @Override public FileVisitResult visitFile(java.nio.file.Path path, BasicFileAttributes attrs)
                    throws java.io.IOException {
                Files.delete(path);
                return FileVisitResult.CONTINUE;
            }
            @Override public FileVisitResult postVisitDirectory(java.nio.file.Path path, java.io.IOException error)
                    throws java.io.IOException {
                if (error != null) throw error;
                Files.delete(path);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    private static byte[] readAll(InputStream in) throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        int count;
        while ((count = in.read(buffer)) != -1) out.write(buffer, 0, count);
        return out.toByteArray();
    }

    private static String hex(byte[] bytes) {
        StringBuilder out = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) out.append(String.format("%02x", b & 255));
        return out.toString();
    }

    private static File path(File root, String relative) { return new File(root, relative); }

    private static void requireExecutable(File root, String relative) throws Exception {
        File file = path(root, relative);
        if (!file.isFile() || !file.canExecute())
            throw new IllegalStateException("Runtime archive is incomplete: executable " + relative);
    }

    private static void requireDirectory(File root, String relative) throws Exception {
        File directory = path(root, relative);
        if (!directory.isDirectory())
            throw new IllegalStateException("Runtime archive is incomplete: directory " + relative);
    }

    private static void validateRuntime(File root) throws Exception {
        if (path(root,"sotcport/run-sotc-bionic.sh").isFile()) {
            requireExecutable(root,"sotcport/run-sotc-bionic.sh");
            for (String rel : new String[]{
                    "sotcport/arm64/bin/sotc-probe",
                    "sotcport/arm64/bin/orbis-pkg-util",
                    "sotcport/arm64/python/bin/python3.13",
                    "sotcport/arm64/lib/libbbgpu.so",
                    "sotcport/arm64/lib/libgow3cpu.so",
                    "sotcport/arm64/lib/libgow3gpu.so",
                    "sotcport/arm64/lib/libgow3present.so",
                    "sotcport/arm64/lib/libc++_shared.so",
                    "sotcport/arm64/python/lib/libpython3.13.so",
                    "sotcport/arm64/drivers/gen8/libvulkan_freedreno.so",
                    "sotcport/scripts/sotc_prepare_game.py",
                    "sotcport/scripts/sotc-upstream/scripts/prepare.py",
                    "runtime-manifest.json"
            }) if (!path(root,rel).isFile())
                throw new IllegalStateException("Incomplete SotC runtime: "+rel);
            requireDirectory(root,"home/sotcport");
            String identity = new String(Files.readAllBytes(path(root,"runtime-manifest.json").toPath()),
                    StandardCharsets.UTF_8);
            if (!identity.contains("\"schema\": 1") ||
                    !identity.contains("\"runtime_backend\": \"bionic\"") ||
                    !identity.contains("\"application_id\": \"com.sotc.android.daedalus\""))
                throw new IllegalStateException("Incompatible Shadow of the Colossus runtime identity");
            return;
        }
        if (path(root,"gow3port/run-bionic.sh").isFile()) {
            boolean sotc = path(root,"gow3port/run-sotc-bionic.sh").isFile();
            if (sotc) {
                requireExecutable(root,"gow3port/run-sotc-bionic.sh");
                if (!path(root,"gow3port/arm64/lib/libbbgpu.so").isFile() ||
                        !path(root,"gow3port/scripts/sotc_prepare_game.py").isFile() ||
                        !path(root,"gow3port/scripts/sotc-upstream/scripts/prepare.py").isFile())
                    throw new IllegalStateException("Incomplete SotC Bionic runtime");
            }
            for (String relative : new String[]{"gow3port/run-bionic.sh", "gow3port/arm64/bin/gow3-probe",
                    "gow3port/arm64/bin/gow3-prepare", "gow3port/arm64/bin/kgsl-chip-id",
                    "gow3port/arm64/bin/orbis-pkg-util", "gow3port/arm64/python/bin/python3.13"}) requireExecutable(root,relative);
            for (String relative : new String[]{"gow3port/arm64/lib/libgow3cpu.so", "gow3port/arm64/lib/libgow3gpu.so",
                    "gow3port/arm64/lib/libgow3present.so", "gow3port/arm64/lib/libc++_shared.so",
                    "gow3port/arm64/python/lib/libpython3.13.so", "gow3port/arm64/drivers/gen8/libvulkan_freedreno.so",
                    "runtime-manifest.json"})
                if (!path(root,relative).isFile()) throw new IllegalStateException("Incomplete Bionic runtime: "+relative);
            String identity = new String(Files.readAllBytes(path(root,"runtime-manifest.json").toPath()),
                    StandardCharsets.UTF_8);
            if (!identity.contains("\"schema\": 1") || !identity.contains("\"runtime_backend\": \"bionic\"") ||
                    !identity.contains("\"application_id\": \"" +
                            (sotc ? "com.sotc.android.daedalus" : "com.gow3.android.bionic") + "\"") ||
                    !identity.contains("\"java_package\": \"ro.cobrabm.fexdroid\""))
                throw new IllegalStateException("Incompatible Bionic runtime identity");
            requireDirectory(root,"home/gow3port"); return;
        }
        requireExecutable(root, "rootfs/bin/sh");
        requireExecutable(root, "rootfs/usr/bin/Xvfb");
        requireExecutable(root, "rootfs/usr/libexec/fxshmd");
        requireExecutable(root, "rootfs/usr/bin/FEX");
        requireExecutable(root, "rootfs/usr/bin/python3.13");
        requireExecutable(root, "gow3port/arm64/bin/gow3-probe");
        requireExecutable(root, "gow3port/arm64/bin/kgsl-chip-id");
        requireExecutable(root, "gow3port/arm64/bin/orbis-pkg-util");
        requireExecutable(root, LOADER);
        requireDirectory(root, "home/gow3port");
        if (path(root, "bbport/rootfs").exists() || path(root, "gow3port/rootfs").exists())
            throw new IllegalStateException("Runtime archive has an invalid nested rootfs layout");
        if (!path(root, "gow3port/arm64/lib/libgow3cpu.so").isFile() ||
                !path(root, "gow3port/arm64/lib/libgow3gpu.so").isFile())
            throw new IllegalStateException("Runtime archive is incomplete: ARM64 libraries");
        File manifest = path(root, "runtime-manifest.json");
        if (!manifest.isFile()) throw new IllegalStateException("Runtime archive is incomplete: manifest");
        String text = new String(Files.readAllBytes(manifest.toPath()), StandardCharsets.UTF_8);
        if (!text.contains("\"schema_version\": 1") ||
                !text.contains("\"application_id\": \"com.gow3.android\"") ||
                !text.contains("\"java_package\": \"ro.cobrabm.fexdroid\""))
            throw new IllegalStateException("Runtime archive is incompatible: manifest identity");

    }

    private static void renameRequired(File source, File target, String label) throws Exception {
        if (!source.exists()) return;
        if (!source.renameTo(target)) throw new IllegalStateException("Cannot stage old " + label);
    }

    private static void preserveUserData(File files, File stage) throws Exception {
        // Home can save settings/import saves before the first game launch.
        // Runtime upgrades replace gow3port, so carry user-owned data into the
        // validated stage before promotion; the old copy remains for rollback.
        boolean sotc = path(stage,"sotcport/run-sotc-bionic.sh").isFile();
        String[] paths = sotc ? new String[]{"sotcport/sotc.ini","sotcport/user","gow3port/user"}
                : new String[]{"gow3port/gow3.ini","gow3port/user","gow3port/Lossless.dll"};
        for (String relative : paths) {
            java.nio.file.Path source = new File(files, relative).toPath();
            java.nio.file.Path target = new File(stage, sotc && relative.equals("gow3port/user") ? "sotcport/user" : relative).toPath();
            if (!Files.exists(source, java.nio.file.LinkOption.NOFOLLOW_LINKS)) continue;
            Files.walkFileTree(source, new SimpleFileVisitor<java.nio.file.Path>() {
                @Override public FileVisitResult preVisitDirectory(java.nio.file.Path dir, BasicFileAttributes attrs)
                        throws java.io.IOException {
                    Files.createDirectories(target.resolve(source.relativize(dir)));
                    return FileVisitResult.CONTINUE;
                }
                @Override public FileVisitResult visitFile(java.nio.file.Path file, BasicFileAttributes attrs)
                        throws java.io.IOException {
                    java.nio.file.Path destination = target.resolve(source.relativize(file));
                    Files.createDirectories(destination.getParent());
                    Files.copy(file, destination, java.nio.file.StandardCopyOption.REPLACE_EXISTING,
                            java.nio.file.LinkOption.NOFOLLOW_LINKS);
                    return FileVisitResult.CONTINUE;
                }
            });
        }
    }

    /** Fill only missing keys; never reset user settings during a runtime upgrade. */
    private static void completeConfig(File root) throws Exception {
        boolean sotc = path(root,"sotcport/run-sotc-bionic.sh").isFile();
        String stem = sotc ? "sotcport/sotc" : "gow3port/gow3";
        File defaults = path(root, stem + ".default.ini");
        File config = path(root, stem + ".ini");
        if (!defaults.isFile()) throw new IllegalStateException("Runtime archive is incomplete: default settings");
        String original = config.isFile()
                ? new String(Files.readAllBytes(config.toPath()), StandardCharsets.UTF_8) : "";
        java.util.Set<String> keys = new java.util.HashSet<>();
        for (String line : original.split("\\r?\\n")) {
            String trimmed = line.trim();
            int equals = trimmed.indexOf('=');
            if (!trimmed.startsWith("#") && equals > 0)
                keys.add(trimmed.substring(0, equals).trim());
        }
        StringBuilder merged = new StringBuilder(original);
        for (String line : Files.readAllLines(defaults.toPath(), StandardCharsets.UTF_8)) {
            String trimmed = line.trim();
            int equals = trimmed.indexOf('=');
            if (trimmed.startsWith("#") || equals <= 0) continue;
            if (keys.add(trimmed.substring(0, equals).trim())) {
                if (merged.length() > 0 && merged.charAt(merged.length() - 1) != '\n') merged.append('\n');
                merged.append(line).append('\n');
            }
        }
        if (merged.toString().equals(original)) return;
        File temporary = new File(config.getPath() + ".defaults.tmp");
        try {
            Files.write(temporary.toPath(), merged.toString().getBytes(StandardCharsets.UTF_8));
            Files.move(temporary.toPath(), config.toPath(), java.nio.file.StandardCopyOption.ATOMIC_MOVE,
                    java.nio.file.StandardCopyOption.REPLACE_EXISTING);
        } finally {
            Files.deleteIfExists(temporary.toPath());
        }
    }

    private static void promote(File files, File stage, String expected) throws Exception {
        File previous = new File(files, ".runtime-previous");
        deleteTree(previous);
        if (!previous.mkdirs()) throw new IllegalStateException("Cannot create runtime rollback directory");
        File oldRoot = new File(previous, "rootfs");
        String portName = path(stage,"sotcport/run-sotc-bionic.sh").isFile() ? "sotcport" : "gow3port";
        File oldPort = new File(previous, portName);
        File oldHome = new File(previous, "home");
        File oldManifest = new File(previous, "runtime-manifest.json");
        File root = new File(files, "rootfs");
        File port = new File(files, portName);
        File home = new File(files, "home");
        File manifest = new File(files, "runtime-manifest.json");
        boolean movedRoot = false, movedPort = false, movedHome = false, movedManifest = false;
        boolean installedRoot = false, installedPort = false, installedHome = false, installedManifest = false;
        try {
            if (root.exists()) { renameRequired(root, oldRoot, "rootfs"); movedRoot = true; }
            if (port.exists()) { renameRequired(port, oldPort, portName); movedPort = true; }
            if (home.exists()) { renameRequired(home, oldHome, "home"); movedHome = true; }
            if (manifest.exists()) { renameRequired(manifest, oldManifest, "manifest"); movedManifest = true; }
            if (new File(stage,"rootfs").exists()) {
                if (!new File(stage,"rootfs").renameTo(root)) throw new IllegalStateException("Cannot promote runtime rootfs");
                installedRoot = true;
            }
            if (!new File(stage, portName).renameTo(port))
                throw new IllegalStateException("Cannot promote "+portName);
            installedPort = true;
            if (!new File(stage, "home").renameTo(home))
                throw new IllegalStateException("Cannot promote runtime home");
            installedHome = true;
            if (!new File(stage, "runtime-manifest.json").renameTo(manifest))
                throw new IllegalStateException("Cannot promote runtime manifest");
            installedManifest = true;
            File marker = new File(files, ".runtime.sha256");
            File markerPart = new File(files, ".runtime.sha256.part");
            Files.write(markerPart.toPath(), (expected + "\n").getBytes(StandardCharsets.US_ASCII));
            if (marker.exists() && !marker.delete()) throw new IllegalStateException("Cannot replace runtime marker");
            if (!markerPart.renameTo(marker)) throw new IllegalStateException("Cannot publish runtime marker");
            deleteTree(previous);
        } catch (Exception error) {
            if (installedManifest) deleteTree(manifest);
            if (installedPort) deleteTree(port);
            if (installedRoot) deleteTree(root);
            if (installedHome) deleteTree(home);
            if (movedManifest && oldManifest.exists()) oldManifest.renameTo(manifest);
            if (movedPort && oldPort.exists()) oldPort.renameTo(port);
            if (movedRoot && oldRoot.exists()) oldRoot.renameTo(root);
            if (movedHome && oldHome.exists()) oldHome.renameTo(home);
            throw error;
        }
    }

    public static synchronized boolean ensure(Context context, File files, Consumer<String> status) throws Exception {
        String expected;
        try (InputStream in = context.getAssets().open("runtime.sha256")) {
            expected = new String(readAll(in), StandardCharsets.US_ASCII).trim();
        } catch (java.io.FileNotFoundException missing) {
            try { validateRuntime(files); completeConfig(files); return false; }
            catch (Exception incomplete) {
                throw new IllegalStateException("This APK does not contain a complete runtime", missing);
            }
        }
        if (!expected.matches("[0-9a-f]{64}")) throw new IllegalStateException("Invalid runtime digest");
        File marker = new File(files, ".runtime.sha256");
        if (marker.isFile() && expected.equals(new String(Files.readAllBytes(marker.toPath()), StandardCharsets.US_ASCII).trim())) {
            try { validateRuntime(files); completeConfig(files); return false; }
            catch (Exception ignored) { /* stale marker: reinstall from the signed asset */ }
        }

        status.accept("Installing Android Bionic runtime…");
        File archive = new File(files, "runtime.tar.gz.part");
        File stage = new File(files, ".runtime-staging-" + expected);
        deleteTree(stage);
        if (!stage.mkdirs()) throw new IllegalStateException("Cannot create runtime staging directory");
        MessageDigest sha = MessageDigest.getInstance("SHA-256");
        try {
            try (InputStream in = context.getAssets().open("runtime.payload");
                 FileOutputStream out = new FileOutputStream(archive)) {
                byte[] buffer = new byte[1024 * 1024];
                int count;
                while ((count = in.read(buffer)) != -1) { sha.update(buffer, 0, count); out.write(buffer, 0, count); }
                out.getFD().sync();
            }
            if (!expected.equals(hex(sha.digest())))
                throw new IllegalStateException("Runtime archive checksum mismatch");
            Process tar = new ProcessBuilder("/system/bin/tar", "-oxzf", archive.getAbsolutePath(),
                    "-C", stage.getAbsolutePath()).redirectErrorStream(true).start();
            byte[] log;
            try (InputStream in = tar.getInputStream()) { log = readAll(in); }
            if (tar.waitFor() != 0)
                throw new IllegalStateException("Runtime extraction failed: " +
                        new String(log, 0, Math.min(log.length, 2048), StandardCharsets.UTF_8));
            validateRuntime(stage);
            preserveUserData(files, stage);
            completeConfig(stage);
            promote(files, stage, expected);
            return true;
        } finally {
            archive.delete();
            deleteTree(stage);
        }
    }

    private RuntimeInstaller() {}
}
