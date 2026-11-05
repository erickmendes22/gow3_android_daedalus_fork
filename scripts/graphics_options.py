#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Startup graphics options of gow3.ini (gpu/shim/gow3_graphics.h) for run.py.

The in-game menu and the launcher write them; run.py turns them into game patches and
environment variables at every start, so "Apply and restart" uses the new values. After a
restart the game confirms them (restart_unconfirmed=0) once it shows frames; when a launch
never did, the next start goes back to the last confirmed values.
"""
import json
from pathlib import Path

# One menu entry per physical resolution; retain the original/old game patches
# and expose the genuinely new, byte-verified CUSA01715 resolutions.
RESOLUTIONS = ('240p', '360p', '424p', '480p', '540p', '720p', '900p',
               'native', '1440p', '1800p', '4K', '8K')
DIRECT_PIXEL_RESOLUTIONS = {
    '240p': '426x240',
    '360p': '640x360',
    '424p': '752x424',
    '540p': '960x540',
}
DIRECT_RESOLUTIONS = frozenset(DIRECT_PIXEL_RESOLUTIONS)
# Old versions exposed the same 480p and 720p twice under raw pixel names.
# Migrate those configurations while preserving the unchanged legacy patches.
LEGACY_RESOLUTION_ALIASES = {
    '426x240': '240p', '640x360': '360p', '752x424': '424p',
    '854x480': '480p', '960x540': '540p', '1280x720': '720p',
    '800p': '900p', '1600x900': '900p',
    '1080p': 'native',
}
def canonical_resolution(value):
    return LEGACY_RESOLUTION_ALIASES.get(value, value)
ENGINE_FPS = (60, 120, 240)
DEFAULTS = {'render_resolution': 'native', 'engine_fps': '120', 'deferred_readback': '1',
            'stale_readback': '1', 'async_shaders': '1', 'expand_video_arena': '1',
            'patch_startup_black_screen': '1'}
RESOLUTION_PREFIX = 'Resolution Patch'
FPS_PREFIX = 'Frame Rate Patch'
TEXTURE_FIX = 'Bug Fix - Texture Corruption Fix'


def read_ini(path):
    values = {}
    try:
        lines = Path(path).read_text(encoding='utf-8').splitlines()
    except OSError:
        return values
    for line in lines:
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip()
    return values


def write_keys(path, updates):
    """Rewrites `updates` in place and appends missing keys, keeping every other line."""
    path = Path(path)
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except OSError:
        lines = ['# gow3 settings (in-game menu: Insert / R3+L2)']
    done, out = set(), []
    for line in lines:
        key = line.split('=', 1)[0].strip() if '=' in line and not line.lstrip().startswith('#') else None
        if key in updates:
            out.append(f'{key}={updates[key]}')
            done.add(key)
        else:
            out.append(line)
    out += [f'{k}={v}' for k, v in updates.items() if k not in done]
    path.write_text('\n'.join(out) + '\n', encoding='utf-8')


def startup_options(ini):
    """The startup options, normalized; unknown values fall back to the defaults."""
    options = {key: ini.get(key, value) for key, value in DEFAULTS.items()}
    options['render_resolution'] = canonical_resolution(options['render_resolution'])
    if options['render_resolution'] not in RESOLUTIONS:
        options['render_resolution'] = 'native'
    if options['engine_fps'] not in {str(f) for f in ENGINE_FPS}:
        options['engine_fps'] = '120'
    for key in ('deferred_readback', 'stale_readback', 'async_shaders', 'expand_video_arena',
                'patch_startup_black_screen'):
        options[key] = '0' if options[key] == '0' else '1'
    return options


def prepare(config, state_path):
    """(options, reverted): the startup options of this launch, restoring the last confirmed
    ones when the previous launch after a restart never confirmed its own."""
    ini = read_ini(config)
    state = {}
    try:
        state = json.loads(Path(state_path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        pass
    options = startup_options(ini)
    reverted = False
    if ini.get('restart_unconfirmed') == '1':
        if state.get('attempt') and state.get('last_good'):
            options = startup_options(state['last_good'])
            write_keys(config, {**options, 'restart_unconfirmed': '0'})
            state['attempt'] = False
            reverted = True
        else:
            state['attempt'] = True
    else:
        state = {'last_good': options, 'attempt': False}
    Path(state_path).write_text(json.dumps(state, indent=2), encoding='utf-8')
    return options, reverted


def patch_names(names, options, texture_fix_available=True):
    """The launcher's patch list with the resolution and frame rate patches of `options`."""
    names = [n for n in names if not n.startswith(RESOLUTION_PREFIX) and not n.startswith(FPS_PREFIX)]
    resolution = options['render_resolution']
    expand_arena = options.get('expand_video_arena', '1') != '0'
    if not expand_arena:
        names = [n for n in names if n != TEXTURE_FIX]
    if resolution != 'native':
        patch_resolution = '720p' if resolution in DIRECT_RESOLUTIONS else resolution
        names = [n for n in names if n != TEXTURE_FIX] + [f'{RESOLUTION_PREFIX} - {patch_resolution}']
    elif expand_arena and texture_fix_available and TEXTURE_FIX not in names:
        names.insert(0, TEXTURE_FIX)
    if options['engine_fps'] != '60':
        names.append(f'{FPS_PREFIX} - {options["engine_fps"]} FPS')
    return names


def environment(options):
    return {'GOW3_DEFERRED_READBACK': options['deferred_readback'],
            'GOW3_STALE_READBACK': options['stale_readback'],
            'GOW3_ASYNC_SHADERS': options['async_shaders'],
            'GOW3_EXPAND_VIDEO_ARENA': options.get('expand_video_arena', '1'),
            'GOW3_STARTUP_BLACK_SCREEN': options.get('patch_startup_black_screen', '1')}
