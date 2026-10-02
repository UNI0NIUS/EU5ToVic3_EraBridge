#pragma once
#include <map>
#include <string>
#include <istream>

namespace EU5
{
struct Religion
{
	int id = -1;
	std::string name;
	std::string definition;
	std::string group;
};
class ReligionManager
{
  public:
	void loadReligions(std::istream& input);
	[[nodiscard]] const auto& getReligions() const { return religions; }
  private:
	std::map<int, Religion> religions;
};
}
