// SPDX-License-Identifier: GPL-2.0-or-later
#include "gow3_png.h"

#include <cstdio>
#include <cstring>
#if defined(__ANDROID__)
#include <dlfcn.h>
#endif

extern "C" {
#include <libavcodec/avcodec.h>
#include <libavutil/error.h>
#include <libswscale/swscale.h>
}

namespace Gow3Png {

namespace {
constexpr int kMaxSide = 4096; // save icons are 228x128; anything far larger is not one

#if defined(__ANDROID__)
// Android 11+ uses the OS's own PNG decoder, avoiding FFmpeg decoder registration
// differences in the native Bionic bundle. The old FFmpeg route remains available
// if libjnigraphics or the specific PNG format is unsupported.
struct NativeDecoder;
struct NativeHeader;
bool DecodeAndroidPng(const unsigned char* data, size_t size, Image& out) {
    void* library = dlopen("libjnigraphics.so", RTLD_NOW | RTLD_LOCAL);
    if (!library) return false;
    using Create = int (*)(const void*, size_t, NativeDecoder**);
    using Destroy = void (*)(NativeDecoder*);
    using GetHeader = const NativeHeader* (*)(const NativeDecoder*);
    using Dimension = int32_t (*)(const NativeHeader*);
    using SetFormat = int (*)(NativeDecoder*, int32_t);
    using Stride = size_t (*)(const NativeDecoder*);
    using Decode = int (*)(NativeDecoder*, void*, size_t, size_t);
    const auto create = reinterpret_cast<Create>(dlsym(library, "AImageDecoder_createFromBuffer"));
    const auto destroy = reinterpret_cast<Destroy>(dlsym(library, "AImageDecoder_delete"));
    const auto header = reinterpret_cast<GetHeader>(dlsym(library, "AImageDecoder_getHeaderInfo"));
    const auto widthOf = reinterpret_cast<Dimension>(dlsym(library, "AImageDecoderHeaderInfo_getWidth"));
    const auto heightOf = reinterpret_cast<Dimension>(dlsym(library, "AImageDecoderHeaderInfo_getHeight"));
    const auto setFormat = reinterpret_cast<SetFormat>(dlsym(library, "AImageDecoder_setAndroidBitmapFormat"));
    const auto strideOf = reinterpret_cast<Stride>(dlsym(library, "AImageDecoder_getMinimumStride"));
    const auto decode = reinterpret_cast<Decode>(dlsym(library, "AImageDecoder_decodeImage"));
    NativeDecoder* decoder = nullptr;
    bool ok = false;
    if (create && destroy && header && widthOf && heightOf && setFormat && strideOf &&
        decode && create(data, size, &decoder) == 0 && decoder) {
        const NativeHeader* info = header(decoder);
        const int width = info ? widthOf(info) : 0;
        const int height = info ? heightOf(info) : 0;
        // ANDROID_BITMAP_FORMAT_RGBA_8888 = 1 (NDK <android/bitmap.h>).
        if (width > 0 && height > 0 && width <= kMaxSide && height <= kMaxSide &&
            setFormat(decoder, 1) == 0) {
            const size_t stride = strideOf(decoder);
            const size_t bytes = stride * size_t(height);
            if (stride >= size_t(width) * 4 && stride <= 64u << 20 &&
                bytes <= 64u << 20 && bytes / size_t(height) == stride) {
                std::vector<unsigned char> pixels(bytes);
                if (decode(decoder, pixels.data(), stride, pixels.size()) == 0) {
                    out.width = width;
                    out.height = height;
                    out.rgba.resize(size_t(width) * size_t(height) * 4);
                    for (int y = 0; y < height; ++y) {
                        std::memcpy(out.rgba.data() + size_t(y) * size_t(width) * 4,
                                    pixels.data() + size_t(y) * stride, size_t(width) * 4);
                    }
                    ok = true;
                    std::printf("Save PNG: Android ImageDecoder RGBA success %dx%d\n", width, height);
                    std::fflush(stdout);
                }
            }
        }
    }
    if (decoder && destroy) destroy(decoder);
    dlclose(library);
    return ok;
}
#endif
}

bool DecodeRgba(const unsigned char* data, size_t size, Image& out) {
    out = {};
    if (!data || !size || size > 64u << 20) {
        return false;
    }
#if defined(__ANDROID__)
    if (DecodeAndroidPng(data, size, out)) return true;
#endif
    const AVCodec* codec = avcodec_find_decoder(AV_CODEC_ID_PNG);
    AVCodecContext* context = codec ? avcodec_alloc_context3(codec) : nullptr;
    AVPacket* packet = av_packet_alloc();
    AVFrame* frame = av_frame_alloc();
    bool ok = context && packet && frame && avcodec_open2(context, codec, nullptr) == 0 &&
              av_new_packet(packet, int(size)) == 0;
    if (!ok) {
        std::printf("Save PNG: decoder setup failed: codec=%d context=%d packet=%d frame=%d, size=%zu\n",
                    codec != nullptr, context != nullptr, packet != nullptr,
                    frame != nullptr, size);
        std::fflush(stdout);
    }
    if (ok) {
        std::memcpy(packet->data, data, size);
        // A PNG is one still-image packet. Do NOT send the EOF/drain packet
        // until the queued image has been received: a second send before the
        // receive can yield AVERROR(EAGAIN), causing valid scene previews to
        // appear as a missing thumbnail. Draining is unnecessary for PNG.
        const int sent = avcodec_send_packet(context, packet);
        const int received = sent == 0 ? avcodec_receive_frame(context, frame) : sent;
        ok = sent == 0 && received == 0 &&
             frame->width > 0 && frame->height > 0 &&
             frame->width <= kMaxSide && frame->height <= kMaxSide;
        if (!ok) {
            char sent_error[AV_ERROR_MAX_STRING_SIZE] = {};
            char recv_error[AV_ERROR_MAX_STRING_SIZE] = {};
            av_strerror(sent, sent_error, sizeof(sent_error));
            av_strerror(received, recv_error, sizeof(recv_error));
            std::printf("Save PNG: FFmpeg send=%d (%s) receive=%d (%s), size=%zu dimensions=%dx%d format=%d\n",
                        sent, sent_error, received, recv_error, size, frame->width, frame->height,
                        int(frame->format));
            std::fflush(stdout);
        }
    }
    if (ok) {
        SwsContext* sws = sws_getContext(frame->width, frame->height, AVPixelFormat(frame->format),
                                         frame->width, frame->height, AV_PIX_FMT_RGBA, SWS_POINT,
                                         nullptr, nullptr, nullptr);
        ok = sws != nullptr;
        if (!ok) {
            std::printf("Save PNG: unsupported swscale format=%d, %dx%d\n",
                        int(frame->format), frame->width, frame->height);
            std::fflush(stdout);
        }
        if (ok) {
            out.width = frame->width;
            out.height = frame->height;
            out.rgba.resize(size_t(out.width) * out.height * 4);
            uint8_t* planes[4] = {out.rgba.data(), nullptr, nullptr, nullptr};
            const int strides[4] = {out.width * 4, 0, 0, 0};
            ok = sws_scale(sws, frame->data, frame->linesize, 0, frame->height, planes, strides) ==
                 frame->height;
            sws_freeContext(sws);
            if (!ok) {
                std::printf("Save PNG: RGBA conversion failed for format=%d, %dx%d\n",
                            int(frame->format), frame->width, frame->height);
                std::fflush(stdout);
            }
        }
    }
    av_frame_free(&frame);
    av_packet_free(&packet);
    avcodec_free_context(&context);
    if (!ok) {
        out = {};
    }
    return ok;
}

bool LoadRgba(const char* path, Image& out) {
    out = {};
    FILE* file = path ? std::fopen(path, "rb") : nullptr;
    if (!file) {
        return false;
    }
    std::vector<unsigned char> bytes;
    unsigned char chunk[65536];
    size_t n;
    while ((n = std::fread(chunk, 1, sizeof(chunk), file)) > 0 && bytes.size() <= (64u << 20)) {
        bytes.insert(bytes.end(), chunk, chunk + n);
    }
    std::fclose(file);
    return DecodeRgba(bytes.data(), bytes.size(), out);
}

} // namespace Gow3Png
