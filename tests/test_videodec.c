/* libSceVideodec: H.264 access units to NV12 pictures (tests/data/tiny.h264: 6 frames of
 * 64x48 testsrc, made with ffmpeg -c:v libx264 -profile:v main -f h264). */
#define _POSIX_C_SOURCE 200809L
#undef NDEBUG /* the checks are asserts; release builds define NDEBUG */
#include "../src/runtime_videodec.c"
#include <assert.h>
#include <stdio.h>

uintptr_t runtime_lookup(const RuntimeExport *table, size_t count, const char *nid) { (void)table; (void)count; (void)nid; return 0; }

static unsigned char frame_buffer[1<<16];
static int pictures, first_luma_sum, seen;

static void check_picture(const PictureInfo *p) {
    if (!p->is_valid) return;
    assert(p->frame_width==64 && p->frame_pitch==64 && p->frame_height==48 && !p->is_error_pic);
    /* B-frames: pictures come in display order, each with its own access unit's data. */
    assert(p->attached_data>=1000 && p->attached_data<1006 && !(seen>>(p->attached_data-1000)&1));
    seen|=1<<(p->attached_data-1000);
    if (!pictures++) for (int i=0;i<64*48;++i) first_luma_sum+=frame_buffer[i];
}


/* Picture() is the only remaining difference between the old sws_scale
 * conversion and Mali's optimized direct YUV420P -> game-owned NV12 path.
 * Compare EVERY output byte, including repeated padded luma/chroma rows.
 * 1920x1080 matches the 4 MiB cinematic buffers from the G720 capture. */
static void test_direct_nv12_bit_exact(void) {
    const int widths[]={64,80,1920};
    const int heights[]={48,50,1080};
    for (int k=0;k<3;++k) {
        const int width=widths[k],height=heights[k];
        AVFrame *frame=av_frame_alloc(), *temporary=av_frame_alloc();
        assert(frame && temporary);
        frame->format=AV_PIX_FMT_YUV420P;
        frame->width=width;
        frame->height=height;
        assert(av_frame_get_buffer(frame,32)==0);
        for (int plane=0;plane<3;++plane) {
            int w=plane ? width/2 : width;
            int h=plane ? height/2 : height;
            for (int y=0;y<h;++y) {
                uint8_t *row=frame->data[plane]+y*frame->linesize[plane];
                for (int x=0;x<w;++x) row[x]=(uint8_t)(x*17+y*11+plane*61);
            }
        }
        Decoder decoder={0};
        decoder.frame=frame;
        decoder.nv12=temporary;
        uint32_t pitch=align((uint32_t)width,64);
        uint32_t rows=align((uint32_t)height,16);
        size_t n=(size_t)pitch*rows*3/2;
        uint8_t *baseline=calloc(1,n+32),*direct=calloc(1,n+32);
        assert(baseline && direct);
        FrameBuffer old_buf={sizeof(FrameBuffer),baseline,n};
        FrameBuffer new_buf={sizeof(FrameBuffer),direct,n};
        PictureInfo old_info={0},new_info={0};
        old_info.this_size=new_info.this_size=sizeof(PictureInfo);
        assert(setenv("GOW3_VIDEODEC_NV12_DIRECT","0",1)==0);
        assert(picture(&decoder,&old_buf,&old_info)==0);
        assert(decoder.fallback_sws_frames==1);
        assert(setenv("GOW3_VIDEODEC_NV12_DIRECT","1",1)==0);
        assert(picture(&decoder,&new_buf,&new_info)==0);
        assert(decoder.direct_nv12_frames==1);
        assert(memcmp(baseline,direct,n+32)==0);
        assert(memcmp(&old_info,&new_info,sizeof(old_info))==0);
        sws_freeContext(decoder.sws);
        av_frame_free(&frame);
        av_frame_free(&temporary);
        free(baseline);
        free(direct);
    }
    assert(unsetenv("GOW3_VIDEODEC_NV12_DIRECT")==0);
}

int main(int argc, char **argv) {
    test_direct_nv12_bit_exact();
    FILE *f=fopen(argc>1 ? argv[1] : "tests/data/tiny.h264","rb");
    assert(f);
    static unsigned char stream[1<<16];
    size_t size=fread(stream,1,sizeof(stream),f);
    fclose(f);

    ConfigInfo config={sizeof(ConfigInfo),0,0,0,64,48,4,0};
    ResourceInfo resource={sizeof(ResourceInfo),0,NULL,0,NULL,0,0};
    assert(videodec_query(&config,&resource)==0 && resource.max_frame_buffer_size>=64*48*3/2);
    assert(videodec_query(NULL,&resource)==ERR_ARGUMENT_POINTER);
    config.this_size=8;
    assert(videodec_query(&config,&resource)==ERR_STRUCT_SIZE);
    config.this_size=sizeof(ConfigInfo);

    Ctrl ctrl={0};
    assert(videodec_create(&config,&resource,&ctrl)==0 && ctrl.handle && ctrl.this_size==sizeof(Ctrl));
    FrameBuffer buffer={sizeof(FrameBuffer),frame_buffer,sizeof(frame_buffer)};
    PictureInfo picture; memset(&picture,0,sizeof(picture)); picture.this_size=sizeof(picture);

    /* Access units as the game's demuxer delivers them. */
    const AVCodec *codec=avcodec_find_decoder(AV_CODEC_ID_H264);
    AVCodecParserContext *parser=av_parser_init(AV_CODEC_ID_H264);
    AVCodecContext *parse_context=avcodec_alloc_context3(codec);
    const unsigned char *p=stream;
    int units=0;
    for (int left=(int)size;;) {
        uint8_t *au; int au_size, flushing=!left; /* a call without input returns the last unit */
        int used=av_parser_parse2(parser,parse_context,&au,&au_size,p,left,AV_NOPTS_VALUE,AV_NOPTS_VALUE,0);
        p+=used; left-=used;
        if (au_size) {
            InputData input={sizeof(InputData),au,(uint64_t)au_size,(uint64_t)units,(uint64_t)units,1000+(uint64_t)units};
            assert(videodec_decode(&ctrl,&input,&buffer,&picture)==0);
            check_picture(&picture);
            ++units;
        }
        if (flushing && !au_size) break;
    }
    av_parser_close(parser);
    avcodec_free_context(&parse_context);
    assert(units==6);
    for (int i=0;i<8;++i) {
        assert(videodec_flush(&ctrl,&buffer,&picture)==0);
        check_picture(&picture);
    }
    assert(pictures==6 && seen==0x3f && first_luma_sum>0);

    /* Errors are codes, not crashes. */
    InputData empty={sizeof(InputData),stream,0,0,0,0};
    assert(videodec_decode(&ctrl,&empty,&buffer,&picture)==ERR_AU_SIZE);
    empty.au_data=NULL; empty.au_size=4;
    assert(videodec_decode(&ctrl,&empty,&buffer,&picture)==ERR_AU_POINTER);
    assert(videodec_decode(NULL,&empty,&buffer,&picture)==ERR_ARGUMENT_POINTER);
    FrameBuffer small={sizeof(FrameBuffer),frame_buffer,16};
    assert(videodec_reset(&ctrl)==0);
    InputData whole={sizeof(InputData),stream,(uint64_t)size,0,0,0};
    int32_t r=videodec_decode(&ctrl,&whole,&small,&picture);
    assert(r==0 || r==ERR_FRAME_BUFFER_SIZE);
    assert(!(r==0 && picture.is_valid));

    assert(videodec_delete(&ctrl)==0 && !ctrl.handle);
    assert(videodec_delete(&ctrl)==ERR_HANDLE);
    puts("videodec test: ok");
    return 0;
}
