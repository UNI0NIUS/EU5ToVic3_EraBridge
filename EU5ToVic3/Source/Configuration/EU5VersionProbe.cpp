#include "EU5VersionProbe.h"
#include <array>
#include <fstream>
#include <regex>
#include <set>
#include <stdexcept>

std::optional<GameVersion> EU5::versionFromExecutable(std::istream& input)
{
	std::array<char, 65536> buffer{};
	std::string overlap;
	std::set<std::string> versions;
	const std::regex branch(R"((?:caesar/)?u[0-9]+q[0-9]+/release/([0-9]+\.[0-9]+\.[0-9]+)[^0-9.])");
	while (input)
	{
		input.read(buffer.data(), buffer.size());
		const auto chunk = overlap + std::string(buffer.data(), static_cast<std::size_t>(input.gcount())) + (input.eof() ? std::string(1, '\0') : "");
		// Search only short neighborhoods, avoiding regex traversal of an entire executable.
		for (auto pos = chunk.find("/release/"); pos != std::string::npos; pos = chunk.find("/release/", pos + 1))
		{
			const auto start = pos > 40 ? pos - 40 : 0;
			const auto candidate = chunk.substr(start, pos + 80 - start);
			for (auto match = std::sregex_iterator(candidate.begin(), candidate.end(), branch); match != std::sregex_iterator{}; ++match)
				versions.insert((*match)[1]);
		}
		overlap = chunk.substr(chunk.size() > 128 ? chunk.size() - 128 : 0);
	}
	if (versions.size() > 1)
		throw std::runtime_error("Conflicting EU5 executable release versions");
	if (versions.empty())
		return std::nullopt;
	return GameVersion(*versions.begin());
}

std::optional<GameVersion> EU5::installedVersion(const std::filesystem::path& gameDirectory)
{
	const auto branch = gameDirectory / "clausewitz_branch.txt";
	if (std::filesystem::is_regular_file(branch))
		if (const auto version = GameVersion::extractVersionFromBranchTxt(branch))
			return version;
	std::ifstream executable(gameDirectory / "../binaries/eu5.exe", std::ios::binary);
	if (!executable)
		return std::nullopt;
	return versionFromExecutable(executable);
}
