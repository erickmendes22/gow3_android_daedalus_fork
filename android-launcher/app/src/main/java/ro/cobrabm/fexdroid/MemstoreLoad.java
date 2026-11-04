// SPDX-License-Identifier: GPL-3.0-only
// Adapted from The412Banner/Bannerlator 0ab047311ccc55b2911d984727d2d57ac6c0ebf7.
package ro.cobrabm.fexdroid;

import java.util.ArrayDeque;

final class MemstoreLoad {
    static final long GIVE_UP_SAMPLES = 5_000L;
    private final long windowMs;
    private final ArrayDeque<long[]> history = new ArrayDeque<>();
    private boolean working;
    private boolean failed;
    private long waited;
    private Integer last;
    MemstoreLoad(long windowMs) { this.windowMs = windowMs; }
    boolean failed() { return failed; }
    Integer percent(long nowMs, long[] counts) {
        if (failed || counts == null || counts.length < 3) return null;
        long[] previous = history.peekLast();
        history.addLast(new long[] {nowMs, counts[0], counts[1], counts[2]});
        while (history.size() > 2) {
            long[] second = secondOldest();
            if (nowMs - second[0] < windowMs) break;
            history.removeFirst();
        }
        if (previous == null) return null;
        long fresh = counts[1] - previous[2];
        if (fresh <= 0) return last;
        if (!working) {
            if (counts[2] > previous[3]) working = true;
            else {
                waited += fresh;
                if (waited >= GIVE_UP_SAMPLES) failed = true;
                return null;
            }
        }
        long[] base = history.peekFirst();
        long samples = counts[1] - base[2];
        if (samples <= 0) return last;
        long p = (counts[0] - base[1]) * 100 / samples;
        last = (int) Math.max(0, Math.min(100, p));
        return last;
    }
    private long[] secondOldest() {
        java.util.Iterator<long[]> it = history.iterator();
        it.next();
        return it.next();
    }
}
