#pragma once
#include "Parser.h"
#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <vector>

namespace EU5
{
using ObjectID = std::uint64_t;
using PopID = ObjectID;
// One saved 0.00001-thousand unit is one hundredth of a person.
using PopulationAmount = std::int64_t;
[[nodiscard]] PopID parsePopID(const std::string& value);
[[nodiscard]] int readEntityID(std::istream& input);
[[nodiscard]] PopulationAmount parsePopulationAmount(const std::string& value);
[[nodiscard]] std::string populationPersons(PopulationAmount value);
[[nodiscard]] std::vector<PopID> readPopIDs(std::istream& input);
[[nodiscard]] std::vector<ObjectID> readObjectIDs(std::istream& input);

struct Population
{
	PopID id = 0;
	std::string type;
	int culture = -1;
	int religion = -1;
	PopulationAmount amount = 0;
	bool sizePresent = false;
	double literacy = 0;
};

class PopulationManager
{
  public:
	void loadPopulations(std::istream& input);
	[[nodiscard]] const auto& getPopulations() const { return populations; }
	[[nodiscard]] const auto& getIgnoredFields() const { return ignoredFields; }
	[[nodiscard]] auto getDeadCount() const { return deadCount; }
  private:
	std::map<PopID, Population> populations;
	std::set<std::string> ignoredFields;
	std::size_t deadCount = 0;
};
}
