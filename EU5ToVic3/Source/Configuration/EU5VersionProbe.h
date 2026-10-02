#pragma once
#include "GameVersion.h"
#include <filesystem>
#include <istream>
#include <optional>

namespace EU5
{
[[nodiscard]] std::optional<GameVersion> versionFromExecutable(std::istream& input);
[[nodiscard]] std::optional<GameVersion> installedVersion(const std::filesystem::path& gameDirectory);
}
