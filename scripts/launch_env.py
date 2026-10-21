#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Shared launch environment for run.py (Windows) and run.sh (Linux).

One source for the graphics options, the selected patches and the direct memory (DMEM) /
VBlank those patches need. The two entry points used to duplicate this and drifted apart: the
Linux run.sh missed the GoW3 graphics defaults and the DMEM, so textures were corrupted and the
game faulted building its heaps.
"""
import os
import sys
from pathlib import Path

PORT = Path(__file__).resolve().parent.parent


def disable_shadows_requested(ini):
    """New positive-toggle setting wins; legacy inverse toggle remains readable."""
    if 'disable_dynamic_shadows' in ini:
        return ini['disable_dynamic_shadows'] == '1'
    return ini.get('effect_dynamic_shadows', '1') == '0'


def derive(game, config, state_path, env):
    """Plan one launch.

    game:       the game folder (eboot.bin)
    config:     gow3.ini path
    state_path: graphics_state.json path (restart confirmation)
    env:        the current environment (GOW3_PATCHES, GOW3_PATCHES_ONLY, explicit overrides)

    Returns:
      updates:     environment variables the graphics options become (GOW3_DEFERRED_READBACK,
                   GOW3_STALE_READBACK, GOW3_ASYNC_SHADERS, GOW3_UPSCALER, GOW3_READBACK_LINEAR)
      patch_names: the selected patch names, resolution and frame rate included
      dmem, vblank: MiB / Hz the selected patches need, or None
      reverted:    a restart never reached the game; the last good options were restored
    """
    sys.path.insert(0, str(PORT / 'scripts'))
    import graphics_options
    from patches import game_profile, game_title_id, patch_profile_status, patch_requirements, selected_patches

    # Upgrade previous duplicated pixel-size entries before preparing the launch
    # state, so both launchers and the persisted ini agree on one canonical name.
    old_ini = graphics_options.read_ini(config)
    previous = old_ini.get('render_resolution')
    if previous is not None:
        canonical = graphics_options.canonical_resolution(previous)
        if canonical != previous:
            graphics_options.write_keys(config, {'render_resolution': canonical})
    graphics, reverted = graphics_options.prepare(config, state_path)
    android_port = env.get('GOW3_ANDROID_PORT') == '1'
    ini = graphics_options.read_ini(config)
    # Earlier Android builds wrote no frames_queued key and silently used one
    # in-flight frame, forcing the CPU submission thread to wait for the GPU
    # once each frame. Use two only when that key is absent; explicit 1/2/0
    # choices remain untouched. The in-game setting still controls latency.
    if android_port and 'frames_queued' not in ini:
        graphics_options.write_keys(config, {'frames_queued': '2'})
        ini = graphics_options.read_ini(config)
    # Bionic opt-in Snapdragon GSR2: unlike the broken old FSR3 Android route,
    # it is an upstream Qualcomm provider. All other upscalers stay disabled.
    # Native AA is GSR2 running with equal input/output dimensions, not GSR2 Off.
    # Preserve the user's provider at every preset, including preset=0.
    # The GPU dispatch path determines whether the scene requires enlargement.
    # GSR2 is kept in the runtime for future work, but 8K is not a GSR2
    # target. The 8K eboot patch must never silently become its 720p fallback.
    gsr2_requested = (android_port and ini.get('upscaler') == 'gsr2' and
                      graphics.get('render_resolution') != '8K')
    if android_port and ini.get('upscaler') not in ('off', 'gsr2'):
        graphics_options.write_keys(config, {'upscaler': 'off', 'preset': '0',
                                             'fsr1': '0', 'rcas': '0'})
        ini = graphics_options.read_ini(config)
    updates = dict(graphics_options.environment(graphics))
    if android_port:
        updates['GOW3_UPSCALER'] = 'gsr2' if gsr2_requested else 'none'
        updates['GOW3_FSR1'] = '0'
        updates['GOW3_RCAS'] = '0'
        updates['GOW3_UPSCALER_SOURCE'] = ('gsr2-native-aa-1to1' if gsr2_requested and
            ini.get('preset', '0').strip() == '0' else
            'gsr2-opt-in' if gsr2_requested else 'disabled-android')
        updates['GOW3_RESOLUTION_STATUS'] = 'native-game-patch'
    elif 'GOW3_UPSCALER' not in env:
        updates['GOW3_UPSCALER'] = 'none'
        updates['GOW3_UPSCALER_SOURCE'] = 'desktop-safe-default'
    if 'GOW3_READBACK_LINEAR' not in env:
        updates['GOW3_READBACK_LINEAR'] = '1'
    updates['GOW3_READBACK_LINEAR_SOURCE'] = (
        'override' if 'GOW3_READBACK_LINEAR' in env else 'android-safe-default')
    identity_check = patch_profile_status(game)
    from patches import CUSA01715_0102_ANDROID_SHA
    # The repaired Native AA samples the real, completed VideoOut frame.
    # For enlarged presets the only equally trustworthy *reduced* source is
    # the verified guest image itself after patching the 01.02 eboot geometry
    # and post-process allocation. A post-hoc 720p downsample offers no GPU gain.
    verified_gsr2_eboot = (gsr2_requested and
        identity_check['title_id'] in ('CUSA01623', 'CUSA01715') and
        identity_check['app_version'] == '01.02' and
        identity_check['eboot_sha256'] == CUSA01715_0102_ANDROID_SHA and
        identity_check['reason'] == 'validated')
    gsr2_preset = ini.get('preset', '0').strip()
    gsr2_native_input_by_preset = {
        '0': ('720p', '1280x720'),
        '1': ('540p', '960x540'),
        '2': ('424p', '752x424'),
        '3': ('360p', '640x360'),
        '4': ('240p', '426x240'),
    }
    if (verified_gsr2_eboot and gsr2_preset in gsr2_native_input_by_preset and
            gsr2_preset != '0'):
        # Launch-only graphics override: no change to the user's stored 720p
        # output choice or the known-good resolution when GSR2 is switched off.
        patch_name, pixel_size = gsr2_native_input_by_preset[gsr2_preset]
        graphics = dict(graphics, render_resolution=patch_name)
        updates['GOW3_GSR2_DIRECT_VIDEOOUT'] = '1'
        updates['GOW3_GSR2_INPUT_RES'] = pixel_size
        updates['GOW3_GSR2_OUTPUT_RES'] = '1280x720'
        updates['GOW3_UPSCALER_SOURCE'] = 'gsr2-verified-videoout'
    resolution = graphics['render_resolution']
    if android_port and resolution in graphics_options.DIRECT_RESOLUTIONS:
        if (identity_check['title_id'] in ('CUSA01623', 'CUSA01715') and
            identity_check['app_version'] == '01.02' and
            identity_check['eboot_sha256'] == CUSA01715_0102_ANDROID_SHA and
            identity_check['reason'] == 'validated'):
            updates['GOW3_PATCH_INPUT_RES'] = graphics_options.DIRECT_PIXEL_RESOLUTIONS[resolution]
            updates['GOW3_RESOLUTION_STATUS'] = 'verified-direct-game-patch'
        else:
            graphics['render_resolution'] = 'native'
            updates['GOW3_RESOLUTION_STATUS'] = 'unsupported-eboot-native-fallback'

    names, dmem, vblank = [], None, None
    shadow_requested = disable_shadows_requested(ini)
    updates['GOW3_SHADOWS_REQUESTED'] = 'off' if shadow_requested else 'on'
    updates['GOW3_SHADOWS_STATUS'] = 'pending' if shadow_requested else 'enabled'
    identity = identity_check
    profile = game_profile(identity['title_id'])
    reason = identity['reason'] or 'unknown'
    if identity['reason'] != 'validated':
        # An unknown Android build must never inherit desktop patch names through an env override.
        if profile is None or identity['eboot_matches'] is False:
            updates['GOW3_PATCH_STATUS'] = identity['reason']
    if profile and identity['reason'] == 'validated':
        try:
            names = selected_patches(profile[1], profile[2], env.get('GOW3_PATCHES', ''),
                                     env.get('GOW3_PATCHES_ONLY') == '1',
                                     startup_black_screen=graphics['patch_startup_black_screen'] != '0')
        except ValueError:
            # Two resolution patches (or another exclusivity violation) cannot both apply.
            names, reason = [], 'patch-conflict'
        if names:
            # gow3.ini decides the resolution and frame rate patches (in-game menu, launcher).
            names = graphics_options.patch_names(names, graphics)
            # GSR2 must match the real eboot-allocated scene, not the desktop
            # default 1920x1080. This retail CUSA01623/01715 01.02 SHA is
            # byte-validated and the actual 720p resolution patch is selected.
            from patches import CUSA01715_0102_ANDROID_SHA
            if (verified_gsr2_eboot and 'Resolution Patch - 720p' in names and
                    gsr2_preset in gsr2_native_input_by_preset):
                if gsr2_preset == '0':
                    # Do not change native AA's existing exact-match 720p path.
                    updates['GOW3_PATCH_INPUT_RES'] = '1280x720'
                    updates['GOW3_RESOLUTION_STATUS'] = 'verified-gsr2-720p-target'
                else:
                    # SHA-verified lower guest raster, separate fixed 720p host.
                    actual_input = gsr2_native_input_by_preset[gsr2_preset][1]
                    updates['GOW3_PATCH_INPUT_RES'] = actual_input
                    updates['GOW3_RESOLUTION_STATUS'] = 'verified-gsr2-videoout-input'
            # This exact-address patch belongs only to the supplied and
            # verified eboot revision. Other builds retain their shadows.
            shadow_reference = '6e72330e9092e5164049b865e5568f2d450904001a73fe0a2f4b39194c195b3c'
            if shadow_requested and identity['eboot_sha256'] == shadow_reference:
                names.append('Disable Dynamic Shadows')
            updates['GOW3_SHADOWS_STATUS'] = ('disabled-patch-selected'
                if 'Disable Dynamic Shadows' in names else
                'unsupported-eboot' if shadow_requested else 'enabled')
            if android_port:
                # Only explicit Android toggles affect their own named patches.
                # Keep mandatory fixes and Home resolution/FPS selection intact.
                optional = {
                    'skip_intro': 'Skip Intro',
                    'patch_skip_video': 'Skip Any Video With X Button',
                    'patch_disable_ssao': 'Disable SSAO',
                    'patch_disable_motion_blur': 'Disable Motion Blur',
                    'patch_disable_dof': 'Disable Depth of Field',
                    'patch_disable_bloom': 'Disable Bloom',
                    'patch_disable_soft_particles': 'Disable Soft Particles',
                }
                for key, patch in optional.items():
                    if key not in ini:
                        continue
                    if ini[key] == '1' and patch not in names:
                        names.append(patch)
                    elif ini[key] != '1':
                        names = [name for name in names if name != patch]
            expand_arena = graphics['expand_video_arena'] != '0'
            dmem, vblank = patch_requirements(profile[1], names, profile[2],
                                              expand_video_arena=expand_arena)
            if not expand_arena:
                from patches import DMEM_RETAIL_MB
                dmem = max(dmem or 0, DMEM_RETAIL_MB)
            # The retail pool plus the patches' extra DMEM must fit the device (design: gate
            # values by device/runtime capability and fail with a clear log, not an OOM kill).
            device_mem = env.get('GOW3_DEVICE_MEM_MB')
            if dmem and device_mem and str(device_mem).isdigit() and dmem > int(device_mem):
                names, dmem, vblank, reason = [], None, None, 'insufficient-memory-budget'
    updates.update({'GOW3_GAME_TITLE': identity['title_id'] or 'unknown',
                    'GOW3_GAME_VERSION': identity['app_version'] or 'unknown',
                    'GOW3_EBOOT_SHA256': identity['eboot_sha256'] or 'unavailable',
                    'GOW3_PATCH_STATUS': reason})
    return {'updates': updates, 'patch_names': names, 'dmem': dmem, 'vblank': vblank,
            'reverted': reverted, 'identity': identity}


def _quote(value):
    return "'" + value.replace("'", "'\\''") + "'"


def main(argv):
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game', required=True, type=Path)
    p.add_argument('--config', required=True, type=Path)
    p.add_argument('--state', required=True, type=Path)
    p.add_argument('--shell', action='store_true',
                   help='print export KEY=VALUE lines (for run.sh) instead of JSON')
    a = p.parse_args(argv)
    plan = derive(a.game, a.config, a.state, dict(os.environ))
    if not a.shell:
        import json
        print(json.dumps(plan))
        return 0
    exports = dict(plan['updates'])
    if plan['patch_names'] or plan['updates'].get('GOW3_PATCH_STATUS') == 'validated':
        exports['GOW3_PATCHES'] = ';'.join(plan['patch_names'])
        exports['GOW3_PATCHES_ONLY'] = '1'
    if plan['dmem']:
        exports['GOW3_DMEM_MB'] = str(plan['dmem'])
    if plan['vblank']:
        exports['GOW3_VBLANK_HZ'] = str(plan['vblank'])
    for key, value in exports.items():
        print(f'export {key}={_quote(str(value))}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
