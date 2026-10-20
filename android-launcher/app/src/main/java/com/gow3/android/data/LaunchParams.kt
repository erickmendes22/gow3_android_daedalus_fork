package com.gow3.android.data

import com.gow3.android.R

/**
 * 一个可编辑的启动参数：其 gow3.ini 键、显示标签、分组以及 Android 运行时
 * 实际消费的取值域。`defaultValue` 是键缺失时 UI 显示的值。
 *
 * 显示标签、分组与说明使用字符串资源 id（labelRes / groupRes / descriptionRes），
 * 由 UI 层通过 Context 解析，数据层保持纯 JVM 结构、不依赖 Android。
 */
internal data class LaunchParam(
    val key: String,
    val labelRes: Int,
    val groupRes: Int,
    val options: List<LaunchOption>,
    val defaultValue: String,
    val descriptionRes: Int? = null,
)

internal data class LaunchOption(val value: String, val labelRes: Int)

/**
 * launcher 编辑的启动参数，由 Android 运行时消费的 gow3.ini 键支撑。
 * 默认值与取值域遵循 `SettingsDialog.java` 的常量（RESOLUTION_VALUES/FPS_VALUES …）
 * 以及 `gpu/shim/gow3_graphics.h` / `gpu/shim/gow3_settings.cpp` 中的运行时解析器；
 * 当两者不一致时（fps_limit：Java 前端提供 40/45，但 `ParseFpsLimit` 把它们映射为 0）
 * 以运行时取值域为准，确保每个选项都实际生效。
 *
 * 各参数的默认值均为移动端优化值（render_resolution=720p、output_res=1280x720、fps_limit=60、
 * engine_fps=60；display_mode 已从可编辑项移除，固定 fullscreen）。这些默认值
 * MUST 与 `tools/android/config/gow3-default.ini`（首启落盘为 gow3.ini 的基准）
 * 保持一致，避免 UI 展示默认与实际运行默认漂移。
 */
internal object LaunchParams {
    val all: List<LaunchParam> = listOf(
        LaunchParam(
            key = "show_fps", labelRes = R.string.param_show_fps,
            groupRes = R.string.param_group_fps,
            options = listOf(LaunchOption("0", R.string.param_option_off),
                LaunchOption("1", R.string.param_option_on)), defaultValue = "0",
        ),
        LaunchParam(
            key = "overlay_corner", labelRes = R.string.param_fps_horizontal,
            groupRes = R.string.param_group_fps,
            options = listOf(LaunchOption("0", R.string.fps_left),
                LaunchOption("4", R.string.fps_center),
                LaunchOption("1", R.string.fps_right)), defaultValue = "1",
        ),
        LaunchParam(
            key = "overlay_anchor_y", labelRes = R.string.param_fps_vertical,
            groupRes = R.string.param_group_fps,
            options = listOf(LaunchOption("0", R.string.fps_top),
                LaunchOption("1", R.string.fps_middle),
                LaunchOption("2", R.string.fps_bottom)), defaultValue = "0",
        ),
        LaunchParam(
            key = "overlay_scale", labelRes = R.string.param_fps_size,
            groupRes = R.string.param_group_fps,
            options = listOf(LaunchOption("50", R.string.fps_size_50),
                LaunchOption("75", R.string.fps_size_75),
                LaunchOption("100", R.string.fps_size_100),
                LaunchOption("125", R.string.fps_size_125),
                LaunchOption("150", R.string.fps_size_150),
                LaunchOption("200", R.string.fps_size_200),
                LaunchOption("250", R.string.fps_size_250),
                LaunchOption("300", R.string.fps_size_300)), defaultValue = "100",
        ),
        LaunchParam(
            key = "android_fullscreen", labelRes = R.string.param_android_fullscreen,
            groupRes = R.string.param_group_display,
            options = listOf(LaunchOption("0", R.string.param_option_off),
                LaunchOption("1", R.string.param_option_on)), defaultValue = "0",
            descriptionRes = R.string.param_desc_android_fullscreen,
        ),
        LaunchParam(
            key = "render_resolution", labelRes = R.string.param_render_resolution,
            groupRes = R.string.param_group_display,
            options = listOf(
                LaunchOption("240p", R.string.param_resolution_240),
                LaunchOption("360p", R.string.param_resolution_360),
                LaunchOption("424p", R.string.param_resolution_424),
                LaunchOption("480p", R.string.param_resolution_480),
                LaunchOption("540p", R.string.param_resolution_540),
                LaunchOption("720p", R.string.param_resolution_720),
                LaunchOption("900p", R.string.param_resolution_900),
                LaunchOption("native", R.string.param_resolution_original),
                LaunchOption("1440p", R.string.param_resolution_1440),
                LaunchOption("1800p", R.string.param_resolution_1800),
                LaunchOption("4K", R.string.param_resolution_4k),
                LaunchOption("8K", R.string.param_resolution_8k),
            ),
            defaultValue = "720p",
            descriptionRes = R.string.param_render_resolution_desc,
        ),
        LaunchParam(
            key = "anisotropy", labelRes = R.string.param_anisotropy,
            groupRes = R.string.param_group_display,
            options = listOf(
                LaunchOption("0", R.string.param_option_game_default),
                LaunchOption("2", R.string.param_option_2x),
                LaunchOption("4", R.string.param_option_4x),
                LaunchOption("8", R.string.param_option_8x),
                LaunchOption("16", R.string.param_option_16x)),
            defaultValue = "0", descriptionRes = R.string.param_desc_anisotropy,
        ),
        LaunchParam(
            key = "fps_limit", labelRes = R.string.param_fps_limit, groupRes = R.string.param_group_performance,
            options = listOf(
                LaunchOption("30", R.string.param_option_30),
                LaunchOption("60", R.string.param_option_60),
                LaunchOption("120", R.string.param_option_120),
                LaunchOption("240", R.string.param_option_240),
                LaunchOption("0", R.string.param_option_unlimited),
            ),
            // 移动端优化默认值：以 60 封顶，避免无限帧率导致发热与耗电。
            // 与 tools/android/config/gow3-default.ini 保持一致。
            defaultValue = "60",
        ),
        LaunchParam(
            key = "engine_fps", labelRes = R.string.param_engine_fps, groupRes = R.string.param_group_performance,
            options = listOf(
                LaunchOption("60", R.string.param_option_engine_60),
                LaunchOption("120", R.string.param_option_120),
                LaunchOption("240", R.string.param_option_240),
            ),
            // 移动端优化默认值：游戏原生引擎速度，最稳定、最省电。
            // 与 tools/android/config/gow3-default.ini 保持一致。
            defaultValue = "60",
            descriptionRes = R.string.param_desc_engine_fps,
        ),
        LaunchParam(
            key = "vsync", labelRes = R.string.param_vsync, groupRes = R.string.param_group_performance,
            options = listOf(
                LaunchOption("0", R.string.param_option_off),
                LaunchOption("1", R.string.param_option_on),
            ),
            defaultValue = "1",
            descriptionRes = R.string.param_desc_vsync,
        ),
        LaunchParam(
            key = "frames_queued", labelRes = R.string.param_frames_queued, groupRes = R.string.param_group_performance,
            options = listOf(
                LaunchOption("1", R.string.param_option_frames_1),
                LaunchOption("2", R.string.param_option_frames_2),
                LaunchOption("0", R.string.param_option_unlimited),
            ),
            defaultValue = "2",
            descriptionRes = R.string.param_desc_frames_queued,
        ),
        LaunchParam(
            key = "skip_network_choice", labelRes = R.string.param_offline_start, groupRes = R.string.param_group_startup,
            options = listOf(
                LaunchOption("0", R.string.param_option_off),
                LaunchOption("1", R.string.param_option_on),
            ),
            defaultValue = "1",
        ),
        LaunchParam(
            key = "debug_camera", labelRes = R.string.param_free_camera, groupRes = R.string.param_group_startup,
            options = listOf(
                LaunchOption("0", R.string.param_option_off),
                LaunchOption("1", R.string.param_option_on),
            ),
            defaultValue = "0",
            descriptionRes = R.string.param_desc_free_camera,
        ),
    )

    /** 参数的当前原始值；缺失或为空时返回其默认值。 */
    fun valueOf(ini: Map<String, String>, param: LaunchParam): String {
        val v = ini[param.key]?.trim()
        if (v.isNullOrEmpty()) return param.defaultValue
        if (param.key != "render_resolution") return v
        // Existing installations may contain pixel-name duplicates. Show the
        // single canonical option without waiting for a game launch to migrate.
        return when (v) {
            "1280x720" -> "720p"
            "854x480" -> "480p"
            "960x540" -> "540p"
            "752x424" -> "424p"
            "640x360" -> "360p"
            "426x240" -> "240p"
            "800p", "1600x900" -> "900p"
            "1080p" -> "native"
            else -> v
        }
    }

    /** 当前值对应的选项；未知值返回 null（由 UI 层回退到原始值）。 */
    fun selectedOption(ini: Map<String, String>, param: LaunchParam): LaunchOption? {
        val v = valueOf(ini, param)
        return param.options.firstOrNull { it.value == v }
    }
}
