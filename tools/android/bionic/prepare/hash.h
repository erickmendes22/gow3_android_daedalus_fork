// Adapted from Bloodborne-Android 2e472653; GoW image format and canonical import names.
#pragma once
#include <array>
#include <string>

#include "pyish.h"

std::string sha256_hex(View d);
std::array<u8, 20> sha1(const u8* d, size_t n);
