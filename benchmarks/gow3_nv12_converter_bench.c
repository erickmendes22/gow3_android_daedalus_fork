/* SPDX-License-Identifier: GPL-2.0-or-later
 * Full 1920x1080 host benchmark of the EXACT GoW3 FFmpeg->guest NV12 path.
 * NOT a measurement of game FPS or Android G720 hardware. */
#define _POSIX_C_SOURCE 200809L
#include "../src/runtime_videodec.c"
#include <time.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

uintptr_t runtime_lookup(const RuntimeExport *table, size_t count, const char *nid) {
    (void)table; (void)count; (void)nid; return 0;
}

static double monotonic_ms(void) {
    struct timespec now;
    assert(clock_gettime(CLOCK_MONOTONIC, &now)==0);
    return now.tv_sec*1000.0 + now.tv_nsec/1000000.0;
}

int main(void) {
    const int width=1920, height=1080, frames=300;
    AVFrame *src=av_frame_alloc(), *intermediate=av_frame_alloc();
    assert(src && intermediate);
    src->width=width; src->height=height;
    src->format=AV_PIX_FMT_YUV420P;
    assert(av_frame_get_buffer(src,32)==0);
    for (int plane=0;plane<3;++plane) {
        const int w=plane ? width/2 : width;
        const int h=plane ? height/2 : height;
        for (int y=0;y<h;++y) {
            unsigned char *dst=src->data[plane]+y*src->linesize[plane];
            for (int x=0;x<w;++x) dst[x]=(uint8_t)(x*17+y*11+plane*61);
        }
    }
    const size_t pitch=align(width,64),rows=align(height,16);
    const size_t size=pitch*rows*3/2;
    unsigned char *dst=calloc(1,size), *ref=calloc(1,size);
    assert(dst && ref);
    Decoder d={0}; d.frame=src; d.nv12=intermediate;
    FrameBuffer output={sizeof(FrameBuffer),dst,size};
    PictureInfo frame_info={0}; frame_info.this_size=sizeof(frame_info);
    assert(setenv("GOW3_VIDEODEC_NV12_DIRECT","0",1)==0);
    assert(picture(&d,&output,&frame_info)==0);
    memcpy(ref,dst,size);
    assert(setenv("GOW3_VIDEODEC_NV12_DIRECT","1",1)==0);
    assert(picture(&d,&output,&frame_info)==0);
    assert(memcmp(ref,dst,size)==0);

    const char *labels[]={"swscale_tmp_copy","direct_guest_nv12"};
    double times[2]={0,0};
    for (int method=0;method<2;++method) {
        assert(setenv("GOW3_VIDEODEC_NV12_DIRECT",method ? "1":"0",1)==0);
        const double start=monotonic_ms();
        for (int i=0;i<frames;++i) {
            const int32_t result=picture(&d,&output,&frame_info);
            if (result) {
                fprintf(stderr,"videodec picture() returned %#x at frame %d\n",result,i);
                return 1;
            }
        }
        times[method]=monotonic_ms()-start;
        fprintf(stdout,"NV12_BENCH mode=%s size=%dx%d frames=%d "
                "total_ms=%.2f avg_ms=%.3f throughput_fps=%.1f\n",
                labels[method],width,height,frames,times[method],
                times[method]/frames,frames*1000.0/times[method]);
    }
    assert(memcmp(ref,dst,size)==0);
    fprintf(stdout,"NV12_BENCH ratio_baseline_over_direct=%.2f "
            "note=conversion_only_not_game_fps\n",times[0]/times[1]);
    sws_freeContext(d.sws);
    av_frame_free(&src);
    av_frame_free(&intermediate);
    free(ref); free(dst);
    return 0;
}
