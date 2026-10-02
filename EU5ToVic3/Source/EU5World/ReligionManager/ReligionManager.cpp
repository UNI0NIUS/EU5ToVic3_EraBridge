#include "ReligionManager.h"
#include "Parser.h"
#include "ParserHelpers.h"
#include "CommonRegexes.h"
#include <stdexcept>

void EU5::ReligionManager::loadReligions(std::istream& input)
{
	Religion current;
	commonItems::parser fields;
	fields.registerKeyword("name", [&](std::istream& stream) { current.name = commonItems::getString(stream); });
	fields.registerKeyword("definition", [&](std::istream& stream) { current.definition = commonItems::getString(stream); });
	fields.registerKeyword("group", [&](std::istream& stream) { current.group = commonItems::getString(stream); });
	fields.IgnoreUnregisteredItems();
	commonItems::parser database;
	database.registerRegex(commonItems::integerRegex, [&](const std::string& key, std::istream& stream) {
		current = Religion{};
		current.id = std::stoi(key);
		fields.parseStream(stream);
		if (current.name.empty() || current.definition.empty())
			throw std::runtime_error("Missing religion name/definition: " + key);
		if (!religions.emplace(current.id, current).second)
			throw std::runtime_error("Duplicate religion ID: " + key);
	});
	database.IgnoreUnregisteredItems();
	commonItems::parser manager;
	manager.registerKeyword("database", [&](std::istream& stream) { database.parseStream(stream); });
	manager.IgnoreUnregisteredItems();
	manager.parseStream(input);
}
