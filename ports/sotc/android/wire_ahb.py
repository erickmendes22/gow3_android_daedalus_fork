#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Wire SotC's OWN Vulkan renderer to the tested GoW3/BB Android AHB presenter.

Run only on a copy staged by stage_renderer.py. No changes to GoW3's core,
SotC's game shaders, or the original SotC PC repository.
"""
from pathlib import Path
import argparse
import shutil

def swap(s, old, new, label):
    n=s.count(old)
    if n!=1: raise RuntimeError(f'{label}: expected one match, got {n}')
    return s.replace(old,new)

def wire(root: Path, gpu: Path):
    root=root.resolve();gpu=gpu.resolve()
    if not (gpu/'shadps4/video_core/renderer_vulkan/vk_presenter.cpp').is_file():
        raise ValueError('Stage the original SotC GPU tree first')
    if gpu == root/'gpu' or gpu in (root/'gpu').parents:
        raise ValueError('Refusing to modify GoW3 GPU source')
    renderer=gpu/'shadps4/video_core/renderer_vulkan'
    shim=gpu/'shim'
    for name in ['vk_swapchain_ahb.cpp','vk_swapchain_ahb.h']:
        shutil.copy2(root/'gpu/shadps4/video_core/renderer_vulkan'/name,renderer/name)
    for name in ['gow3_present_client.cpp','gow3_present_client.h',
                 'vk_driver_loader.cpp','vk_driver_loader.h']:
        shutil.copy2(root/'gpu/shim'/name,shim/name)
    shutil.copy2(root/'tools/android/present/gow3_present_proto.h',shim/'gow3_present_proto.h')

    # No SDL or VkSurfaceKHR in the game process. AHardwareBuffers are
    # presented by the APK via the UNIX domain socket protocol.
    path=renderer/'vk_swapchain.h'
    content=path.read_text()
    path.write_text('#ifdef __ANDROID__\n'
        '#include "video_core/renderer_vulkan/vk_swapchain_ahb.h"\n'
        '#else\n'+content+'\n#endif\n')
    path=renderer/'vk_swapchain.cpp'
    content=path.read_text()
    path.write_text('#ifndef __ANDROID__\n'+content+'\n#endif\n')

    ahb=renderer/'vk_swapchain_ahb.cpp'
    content=ahb.read_text()
    content=swap(content,'#include "gow3_settings.h"',
                 '// SotC uses the socket fifo mode, not GoW3 settings.', 'AHB settings include')
    content=swap(content,'#include "imgui/renderer/imgui_core.h"',
                 '// HUD is rendered by SotC BbOverlay.', 'AHB imgui include')
    content=swap(content,'Gow3Settings::Get().vsync.load()',
                 'Gow3Present::Client::VsyncRequested()', 'AHB FIFO connection')
    content=swap(content,'Gow3Settings::Get().vsync;',
                 'Gow3Present::Client::VsyncRequested();', 'AHB FIFO changes')
    content=content.replace('GOW3_PRESENT_BUFFERS','SOTC_PRESENT_BUFFERS')
    ahb.write_text(content)

    # The app's socket protocol is intentionally shared. Prefer a SotC
    # socket, but let the GoW3 test launcher consume the same frames.
    client=shim/'gow3_present_client.cpp'
    content=client.read_text()
    content=swap(content,'const char* path = std::getenv("GOW3_PRESENT_SOCKET");',
                 '''const char* path=std::getenv("SOTC_PRESENT_SOCKET");
    if (!path || !*path) path=std::getenv("GOW3_PRESENT_SOCKET");''',
                 'SotC app frame socket')
    content=swap(content,'const char* value = std::getenv("GOW3_VSYNC");',
                 '''const char* value=std::getenv("SOTC_VSYNC");
    if (!value) value=std::getenv("GOW3_VSYNC");''',
                 'SotC app VSync')
    client.write_text(content)

    platform=renderer/'vk_platform.cpp'
    content=platform.read_text()
    content=swap(content,'#include <vector>',
                 '#include <vector>\n#ifdef __ANDROID__\n#include "vk_driver_loader.h"\n#endif',
                 'Android Vulkan direct driver')
    old='''    static vk::detail::DynamicLoader dl;
    // sotc: SOTC_DLSSG=1 loads Vulkan through Streamline's interposer (DLSS Frame Generation).
    PFN_vkGetInstanceProcAddr get_instance_proc_addr = Dlssg::LoadInterposer();
    if (!get_instance_proc_addr) {
        get_instance_proc_addr =
            dl.getProcAddress<PFN_vkGetInstanceProcAddr>("vkGetInstanceProcAddr");
    }
    VULKAN_HPP_DEFAULT_DISPATCHER.init(get_instance_proc_addr);'''
    new='''#ifdef __ANDROID__
    PFN_vkGetInstanceProcAddr get_instance_proc_addr=
        reinterpret_cast<PFN_vkGetInstanceProcAddr>(gow3_vk_get_instance_proc_addr());
    ASSERT_MSG(get_instance_proc_addr, "SotC Android selected Vulkan driver could not be loaded");
#else
    static vk::detail::DynamicLoader dl;
    PFN_vkGetInstanceProcAddr get_instance_proc_addr=Dlssg::LoadInterposer();
    if (!get_instance_proc_addr)
        get_instance_proc_addr=dl.getProcAddress<PFN_vkGetInstanceProcAddr>(
            "vkGetInstanceProcAddr");
#endif
    VULKAN_HPP_DEFAULT_DISPATCHER.init(get_instance_proc_addr);'''
    content=swap(content,old,new,'Vulkan instance driver loader')
    platform.write_text(content)

    device=renderer/'vk_instance.cpp'
    content=device.read_text()
    old='''    ASSERT_MSG(add_extension(VK_KHR_SWAPCHAIN_EXTENSION_NAME),
               "Required Vulkan extension unavailable: {}", VK_KHR_SWAPCHAIN_EXTENSION_NAME);'''
    new='''#ifdef __ANDROID__
    for(const char* extension : {VK_ANDROID_EXTERNAL_MEMORY_ANDROID_HARDWARE_BUFFER_EXTENSION_NAME,
                                 VK_EXT_QUEUE_FAMILY_FOREIGN_EXTENSION_NAME,
                                 VK_KHR_EXTERNAL_SEMAPHORE_FD_EXTENSION_NAME}) {
        ASSERT_MSG(add_extension(extension), "Required SotC AHB presentation extension unavailable: {}",
                   extension);
    }
#else
    ASSERT_MSG(add_extension(VK_KHR_SWAPCHAIN_EXTENSION_NAME),
               "Required Vulkan extension unavailable: {}", VK_KHR_SWAPCHAIN_EXTENSION_NAME);
#endif'''
    content=swap(content,old,new,'Vulkan AHB driver extensions')
    device.write_text(content)

    presenter=renderer/'vk_presenter.cpp'
    content=presenter.read_text()
    # Desktop warm-up paints temporary frames on a second thread while the
    # presenter is still being constructed. The AHB swapchain cannot safely
    # submit frames from that thread before Android renderer initialization
    # completes. On Android, warm up the cache synchronously instead. This
    # preserves the complete original game-frame presentation path.
    content=swap(content,
        '''    std::atomic<bool> warming{true};
    std::thread painter([this, &warming] {
        while (warming.load(std::memory_order_relaxed)) {
            Present(PrepareBlankFrame(true), false, false);
            std::this_thread::sleep_for(std::chrono::milliseconds(33));
        }
    });''',
        '''#ifndef __ANDROID__
    std::atomic<bool> warming{true};
    std::thread painter([this, &warming] {
        while (warming.load(std::memory_order_relaxed)) {
            Present(PrepareBlankFrame(true), false, false);
            std::this_thread::sleep_for(std::chrono::milliseconds(33));
        }
    });
#endif''',
        'disable premature Android AHB warm-up presenter thread')
    content=swap(content,
        '''    warming.store(false, std::memory_order_relaxed);
    painter.join();''',
        '''#ifndef __ANDROID__
    warming.store(false, std::memory_order_relaxed);
    painter.join();
#endif''',
        'finish desktop-only warm-up thread')
    content=swap(content,'const vk::ImageView swapchain_image_view = swapchain.ImageView();',
        '''const vk::ImageView swapchain_image_view = swapchain.ImageView();
    const auto sotc_acquire_queues = swapchain.AcquireQueues();
    const auto sotc_release_queues = swapchain.ReleaseQueues();''',
        'AHB presenter queues')
    content=swap(content,'''                .oldLayout = vk::ImageLayout::eUndefined,
                .newLayout = vk::ImageLayout::eColorAttachmentOptimal,
                .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                .image = swapchain_image,''',
        '''                .oldLayout = vk::ImageLayout::eUndefined,
                .newLayout = vk::ImageLayout::eColorAttachmentOptimal,
                .srcQueueFamilyIndex = sotc_acquire_queues.first,
                .dstQueueFamilyIndex = sotc_acquire_queues.second,
                .image = swapchain_image,''',
        'AHB acquire ownership')
    content=swap(content,'''            .oldLayout = post_old_layout,
            .newLayout = vk::ImageLayout::ePresentSrcKHR,
            .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
            .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
            .image = swapchain_image,''',
        '''            .oldLayout = post_old_layout,
            .newLayout = swapchain.PresentLayout(),
            .srcQueueFamilyIndex = sotc_release_queues.first,
            .dstQueueFamilyIndex = sotc_release_queues.second,
            .image = swapchain_image,''',
        'AHB release ownership')
    content=swap(content,'''            .oldLayout = from,
            .newLayout = to,
            .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
            .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
            .image = swapchain_image,''',
        '''            .oldLayout = from,
            .newLayout = to,
            .srcQueueFamilyIndex = from==vk::ImageLayout::eUndefined
                                    ? swapchain.AcquireQueues().first
                                    : to==swapchain.PresentLayout()
                                        ? swapchain.ReleaseQueues().first : VK_QUEUE_FAMILY_IGNORED,
            .dstQueueFamilyIndex = from==vk::ImageLayout::eUndefined
                                    ? swapchain.AcquireQueues().second
                                    : to==swapchain.PresentLayout()
                                        ? swapchain.ReleaseQueues().second : VK_QUEUE_FAMILY_IGNORED,
            .image = swapchain_image,''',
        'AHB FSR generated-frame queue ownership')
    if content.count('vk::ImageLayout::ePresentSrcKHR')!=1:
        raise RuntimeError('Unexpected number of remaining desktop present layouts')
    content=content.replace('vk::ImageLayout::ePresentSrcKHR',
                            'swapchain.PresentLayout()')
    if content.count('info.AddWait(swapchain.GetImageAcquiredSemaphore());')!=2:
        raise RuntimeError('Expected two optional AHB acquired-semaphore waits')
    content=content.replace('info.AddWait(swapchain.GetImageAcquiredSemaphore());',
       'if (auto acquired = swapchain.GetImageAcquiredSemaphore()) info.AddWait(acquired);')
    presenter.write_text(content)
    print('Wired SotC Vulkan renderer to Android AHB, Turnip loader and APK frame socket')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--gpu',type=Path,required=True)
    args=p.parse_args()
    wire(args.root,args.gpu)
if __name__=='__main__': main()
