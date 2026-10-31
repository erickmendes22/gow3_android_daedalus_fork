// Minimal logging shim for the *standalone shader generator test only*.
// Production SotC keeps its real logging implementation, unchanged.
#pragma once
#define LOG_CRITICAL(...) ((void)0)
#define LOG_ERROR(...) ((void)0)
#define LOG_WARNING(...) ((void)0)
#define LOG_INFO(...) ((void)0)
#define LOG_DEBUG(...) ((void)0)
#define LOG_TRACE(...) ((void)0)
#define LOG_GENERIC(...) ((void)0)
