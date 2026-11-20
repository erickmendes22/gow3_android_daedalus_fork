package ro.cobrabm.fexdroid;

/**
 * Vulkan output buffer size, not the Android SurfaceView size.
 *
 * The compositor scales this smaller AHardwareBuffer to the device screen.
 * The game renders to its separately prepared internal resolution; the
 * presenter handles cinematic bars and Fit/Fill within this small buffer.
 */
final class Order1886OutputSize {
    private Order1886OutputSize() {}

    static int[] forSurface(int physicalW, int physicalH, int gameRenderW) {
        if(physicalW<320||physicalH<180)
            throw new IllegalArgumentException("Surface too small");
        if(gameRenderW!=1280&&gameRenderW!=1600&&gameRenderW!=1920)
            throw new IllegalArgumentException("Unsupported render width");
        // 1280 = 720p, 1600 = 900p, 1920 = 1080p, always true 16:9 AHBs.
        final int targetW=gameRenderW;
        final int targetH=gameRenderW*9/16;
        if(physicalW>=targetW && physicalH>=targetH)
            return new int[]{targetW,targetH};
        // On a lower-resolution physical display avoid oversized buffers,
        // while keeping their aspect; even dimensions satisfy most grallocs.
        final double scale=Math.min((double)physicalW/targetW,
                                    (double)physicalH/targetH);
        final int w=Math.max(320,((int)Math.floor(targetW*scale)/2)*2);
        final int h=Math.max(180,((int)Math.floor(targetH*scale)/2)*2);
        return new int[]{Math.min(physicalW,w),Math.min(physicalH,h)};
    }
}
