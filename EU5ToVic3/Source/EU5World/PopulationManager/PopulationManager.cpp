#include "PopulationManager.h"
#include "CommonRegexes.h"
#include "ParserHelpers.h"
#include <charconv>
#include <iomanip>
#include <limits>
#include <sstream>
#include <stdexcept>

EU5::PopID EU5::parsePopID(const std::string& value)
{
	PopID id = 0;
	const auto [end, error] = std::from_chars(value.data(), value.data() + value.size(), id);
	if (error != std::errc{} || end != value.data() + value.size() || id > std::numeric_limits<std::uint32_t>::max())
		throw std::runtime_error("Invalid EU5 population ID: " + value);
	return id;
}

EU5::PopulationAmount EU5::parsePopulationAmount(const std::string& value)
{
	const auto dot = value.find('.');
	const auto whole = value.substr(0, dot);
	auto fraction = dot == std::string::npos ? std::string{} : value.substr(dot + 1);
	if (whole.empty() || fraction.size() > 5 || whole.find_first_not_of("0123456789") != std::string::npos ||
		 fraction.find_first_not_of("0123456789") != std::string::npos)
		throw std::runtime_error("Invalid EU5 population size: " + value);
	fraction.append(5 - fraction.size(), '0');
	PopulationAmount amount = 0;
	const auto fixed = whole + fraction;
	const auto [end, error] = std::from_chars(fixed.data(), fixed.data() + fixed.size(), amount);
	if (error != std::errc{} || end != fixed.data() + fixed.size())
		throw std::runtime_error("EU5 population size overflow: " + value);
	return amount;
}

int EU5::readEntityID(std::istream& input)
{
	const auto value = parsePopID(commonItems::getString(input));
	if (value > static_cast<PopID>(std::numeric_limits<int>::max()))
		throw std::runtime_error("Entity ID exceeds this model's supported range");
	return static_cast<int>(value);
}

std::string EU5::populationPersons(const PopulationAmount value)
{
	std::ostringstream output;
	output << value / 100 << '.' << std::setw(2) << std::setfill('0') << value % 100;
	return output.str();
}

std::vector<EU5::PopID> EU5::readPopIDs(std::istream& input)
{
	return readObjectIDs(input);
}

std::vector<EU5::ObjectID> EU5::readObjectIDs(std::istream& input)
{
	std::vector<PopID> ids;
	for (const auto& value: commonItems::getStrings(input))
		ids.push_back(parsePopID(value));
	return ids;
}

void EU5::PopulationManager::loadPopulations(std::istream& input)
{
	Population current;
	std::set<std::string> seen;
	commonItems::parser fields;
	auto unique = [&seen](const std::string& key) {
		if (!seen.insert(key).second)
			throw std::runtime_error("Duplicate population field: " + key);
	};
	fields.registerKeyword("type", [&](std::istream& stream) { unique("type"); current.type = commonItems::getString(stream); });
	fields.registerKeyword("culture", [&](std::istream& stream) { unique("culture"); current.culture = readEntityID(stream); });
	fields.registerKeyword("religion", [&](std::istream& stream) { unique("religion"); current.religion = readEntityID(stream); });
	fields.registerKeyword("size", [&](std::istream& stream) {
		unique("size"); current.amount = parsePopulationAmount(commonItems::getString(stream)); current.sizePresent = true;
	});
	fields.registerKeyword("literacy", [&](std::istream& stream) { unique("literacy"); current.literacy = commonItems::getDouble(stream); });
	fields.IgnoreAndStoreUnregisteredItems(ignoredFields);
	std::set<PopID> ids;
	commonItems::parser database;
	database.registerRegex(commonItems::integerRegex, [&](const std::string& key, std::istream& stream) {
		const auto id = parsePopID(key);
		if (!ids.insert(id).second || populations.contains(id))
			throw std::runtime_error("Duplicate population ID: " + key);
		commonItems::parser::getNextTokenWithoutMatching(stream); // equals
		stream >> std::ws;
		if (stream.peek() != '{')
		{
			if (commonItems::parser::getNextTokenWithoutMatching(stream) != "none")
				throw std::runtime_error("Unexpected population sentinel: " + key);
			++deadCount;
			return;
		}
		current = Population{};
		current.id = id;
		seen.clear();
		fields.parseStream(stream);
		if (current.type.empty() || current.culture < 0 || current.religion < 0)
			throw std::runtime_error("Missing required population type/culture/religion at ID " + key);
		populations.emplace(id, std::move(current));
	});
	database.registerRegex(commonItems::catchallRegex, [](const std::string& key, std::istream&) {
		throw std::runtime_error("Invalid population database key: " + key);
	});
	commonItems::parser manager;
	manager.registerKeyword("database", [&](std::istream& stream) { database.parseStream(stream); });
	manager.IgnoreUnregisteredItems();
	manager.parseStream(input);
}
