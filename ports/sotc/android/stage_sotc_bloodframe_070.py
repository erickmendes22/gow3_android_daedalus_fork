#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bloodframe 2.0 real generated frames for SotC's Android AHardwareBuffer WSI.

Run AFTER stage_renderer.py and wire_ahb.py. Clone only Bloodborne's tested
separate-VkDevice / AHB / sync-fd engine. The in-game frame is retained, and
each Bloodframe output is separately submitted via the native Vulkan renderer
and AHB socket, FIFO-queued before the original game frame.
No fake frame interpolation, duplicate image or FPS counter substitution.
"""
from pathlib import Path
import argparse, shutil

def exact(text,needle,replace,label):
    n=text.count(needle)
    if n!=1:raise ValueError(f"Bloodframe {label}: expected 1 anchor, found {n}")
    return text.replace(needle,replace)

def stage(root:Path,gpu:Path):
    root=root.resolve();gpu=gpu.resolve()
    renderer=gpu/'shadps4/video_core/renderer_vulkan'
    shim=gpu/'shim'
    assert (renderer/'vk_presenter.cpp').is_file()
    assert (renderer/'vk_swapchain_ahb.h').is_file(), "AHB must be wired first"
    vendor=root/'ports/sotc/android/bloodframe'
    for name in ('bb_lsfg_state.cpp','bb_lsfg_state.h','bb_lsfg.h'):
        shutil.copy2(vendor/name,shim/name)
    for name in ('vk_lsfg.cpp','vk_lsfg.h','vk_frame_latency.cpp','vk_frame_latency.h'):
        shutil.copy2(vendor/name,renderer/name)
    # Native API uses the official Bloodframe v2 C ABI, dlopened only when FG
    # is enabled; no Lossless.dll is ever included in the application.
    header=renderer/'vk_presenter.h'
    h=header.read_text()
    h=exact(h,'class Presenter {','class Lsfg;\nclass Presenter {','presenter declaration')
    h=exact(h,'    bool PresentGenerated(Frame* frame);',
        '''    bool PresentGenerated(Frame* frame);
#ifdef __ANDROID__
    bool PresentBloodframe(Frame* frame, vk::Image generated, vk::Semaphore ready);
#endif''','present helper')
    h=exact(h,'    Swapchain swapchain;','    Swapchain swapchain;\n#ifdef __ANDROID__\n    std::unique_ptr<Lsfg> lsfg;\n#endif','Bloodframe member')
    header.write_text(h)
    present=renderer/'vk_presenter.cpp'
    t=present.read_text()
    t=exact(t,'#include "video_core/renderer_vulkan/vk_presenter.h"',
        '#include "video_core/renderer_vulkan/vk_presenter.h"\n#ifdef __ANDROID__\n#include "video_core/renderer_vulkan/vk_lsfg.h"\n#include "bb_lsfg_state.h"\n#endif', 'headers')
    t=exact(t,'    const u32 num_images = swapchain.GetImageCount();',
        '''#ifdef __ANDROID__
    // Process every real game frame through Bloodframe only on explicit opt-in.
    // The native engine uses the same Turnip proc-address table as the game.
    lsfg=Lsfg::Create(instance,BbLsfgState::Initial());
    if (lsfg) std::fprintf(stderr,
        "SOTC BLOODFRAME: ACTIVE x%u actual AHB generated frames, game FPS unchanged\\n",
        lsfg->Multiplier());
#endif
    const u32 num_images = swapchain.GetImageCount();''','ctor')
    t=exact(t,
        '''    // sotc: FSR 3 frame generation: the frame between the last game frame and this one first,''',
        '''#ifdef __ANDROID__
    // Bloodframe's Vulkan device exports a sync-fd for each generated frame.
    // Consume it on THIS device, acquire queue-family EXTERNAL, then present
    // the generated AHB before the original frame with correct FIFO pacing.
    if (lsfg && is_game_frame && !is_reusing_frame) {
        const int n=lsfg->ProcessFrame(present_scheduler,frame->image,frame->width,
            frame->height,frame->ready_semaphore,frame->ready_tick);
        if (n<0) {
            std::fprintf(stderr,"SOTC BLOODFRAME: failed; disabled for rest of game\\n");
            lsfg.reset();
        } else {
            for (int i=0;i<n;i++) {
                const auto& out=lsfg->GetOutput(static_cast<u32>(i));
                if (!PresentBloodframe(frame,out.image,out.wait)) {
                    std::fprintf(stderr,"SOTC BLOODFRAME: presentation failed; disabling\\n");
                    lsfg.reset();
                    break;
                }
                const u64 tick=present_scheduler.CurrentTick()-1;
                lsfg->OutputSubmitted(static_cast<u32>(i),tick);
            }
        }
    }
#endif
    // sotc: FSR 3 frame generation: the frame between the last game frame and this one first,''',
        'game present hook')
    # Reuse the exact original *already Android AHB-patched* generated present
    # pipeline, including swapchain queue family ownership and screenshot path.
    prefix='bool Presenter::PresentGenerated(Frame* frame) {'
    begin=t.find(prefix)
    end=t.find('Frame* Presenter::GetRenderFrame()',begin)
    if begin<0 or end<0:raise ValueError('SotC framegen body drift')
    original=t[begin:end]
    cloned=original.replace(prefix,
        'bool Presenter::PresentBloodframe(Frame* frame, vk::Image generated, vk::Semaphore wait) {',1)
    prep='''    auto& scheduler = present_scheduler;
    const auto cmdbuf = scheduler.CommandBuffer();
    const vk::Image generated =
        FsrFg::Generate(cmdbuf, frame->id, frame->image, frame->width, frame->height,
                        frame->hudless ? frame->hudless->image : vk::Image{});

    // FSR 3 reads the game frame and its inputs: after the frame's own commands.
    if (frame->ready_semaphore == draw_scheduler.GetWorkSemaphore()->Handle()) {
        draw_scheduler.WaitSubmitted(frame->ready_tick, false);
    }
    SubmitInfo info{};
    info.AddWait(frame->ready_semaphore, frame->ready_tick);
    const auto submit = [&] {
        const u64 tick = scheduler.CurrentTick();
        scheduler.Flush(info);
        FsrFg::Submitted(scheduler, tick);
    };
    if (!generated) {
        submit(); // FSR 3 history only (first frame, after a cut)
        return false;
    }'''
    cloneprep='''    if (!generated) return false;
    auto& scheduler=present_scheduler;
    const auto cmdbuf=scheduler.CommandBuffer();
    SubmitInfo info{};
    // Imported sync-file semaphore from Bloodframe's independent Vulkan device.
    if (wait) info.AddWait(wait);
    const auto submit=[&] { scheduler.Flush(info); };'''
    cloned=exact(cloned,prep,cloneprep,'FSR generate block replacement')
    cloned=exact(cloned,'    FsrFg::NotePresent();\n','', 'FSR statistics removal')
    acquire='''    cmdbuf.blitImage(generated, vk::ImageLayout::eGeneral, swapchain_image,
                     vk::ImageLayout::eTransferDstOptimal, blit, vk::Filter::eLinear);'''
    external='''    const vk::ImageSubresourceRange src_range{
        .aspectMask=vk::ImageAspectFlagBits::eColor,.baseMipLevel=0,.levelCount=1,
        .baseArrayLayer=0,.layerCount=1,
    };
    const u32 graphics=instance.GetGraphicsQueueFamilyIndex();
    const vk::ImageMemoryBarrier source_acquire{
        .srcAccessMask=vk::AccessFlagBits::eNone,
        .dstAccessMask=vk::AccessFlagBits::eTransferRead,
        .oldLayout=vk::ImageLayout::eGeneral,
        .newLayout=vk::ImageLayout::eTransferSrcOptimal,
        .srcQueueFamilyIndex=VK_QUEUE_FAMILY_EXTERNAL,
        .dstQueueFamilyIndex=graphics,
        .image=generated,.subresourceRange=src_range,
    };
    cmdbuf.pipelineBarrier(vk::PipelineStageFlagBits::eAllCommands,
        vk::PipelineStageFlagBits::eTransfer,
        vk::DependencyFlagBits::eByRegion,{}, {}, source_acquire);
    cmdbuf.blitImage(generated, vk::ImageLayout::eTransferSrcOptimal,
        swapchain_image,vk::ImageLayout::eTransferDstOptimal,blit,vk::Filter::eLinear);
    const vk::ImageMemoryBarrier source_release{
        .srcAccessMask=vk::AccessFlagBits::eTransferRead,
        .dstAccessMask=vk::AccessFlagBits::eNone,
        .oldLayout=vk::ImageLayout::eTransferSrcOptimal,
        .newLayout=vk::ImageLayout::eGeneral,
        .srcQueueFamilyIndex=graphics,
        .dstQueueFamilyIndex=VK_QUEUE_FAMILY_EXTERNAL,
        .image=generated,.subresourceRange=src_range,
    };
    cmdbuf.pipelineBarrier(vk::PipelineStageFlagBits::eTransfer,
        vk::PipelineStageFlagBits::eAllCommands,
        vk::DependencyFlagBits::eByRegion,{}, {}, source_release);'''
    cloned=exact(cloned,acquire,external,'external output barriers')
    # Bloodframe uses its own stats; leave the original FSR 3 code and its
    # non-Bloodframe logic untouched in the original method.
    t=t[:end]+'#ifdef __ANDROID__\n'+cloned+'#endif // Android Bloodframe AHB output\n\n'+t[end:]
    present.write_text(t)
    print("SOTC BLOODFRAME: real Vulkan AHB output path staged; two queue-family ownership transfers per generated frame")

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--gpu',type=Path,required=True)
    args=p.parse_args()
    stage(args.root,args.gpu)
if __name__=="__main__":main()
