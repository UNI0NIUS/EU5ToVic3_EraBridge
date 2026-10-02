from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import re
from pdx_text import root
from converter_command_capacity import render,install,EFFECT,ON_ACTIONS,SCRIPT,STATIC,MODIFIERS


class CommandCapacityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.game=Path(self.tmp.name)/'game';self.mod=Path(self.tmp.name)/'mod'
        for rel,text in {
            'common/technology/technologies/military.txt':'early={modifier={country_general_rank_impact_mult=0.2}} late={modifier={country_general_rank_impact_mult=0.4 country_admiral_rank_impact_mult=0.25}}',
            ON_ACTIONS:'on_game_started={effect={original_start=yes}} on_monthly_pulse_country={effect={original_month=yes} events={unrelated.1}} on_acquired_technology={effect={original_tech=yes}} unrelated={effect={leave=yes}}',
        }.items():
            path=self.game/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)

    def test_preserves_existing_actions_and_is_idempotent(self):
        install(self.game,self.mod);first=(self.mod/ON_ACTIONS).read_text(encoding='utf-8-sig')
        install(self.game,self.mod);second=(self.mod/ON_ACTIONS).read_text(encoding='utf-8-sig')
        self.assertEqual(first,second)
        for token in ('original_start=yes','original_month=yes','original_tech=yes','unrelated.1','leave=yes'):self.assertIn(token,second)
        self.assertEqual(second.count(EFFECT),3)
        self.assertIn('every_country',root(second).fields()['on_game_started'].text())

    def test_existing_mod_on_actions_not_replaced_by_vanilla(self):
        path=self.mod/ON_ACTIONS;path.parent.mkdir(parents=True)
        path.write_text((self.game/ON_ACTIONS).read_text().replace('original_start=yes','user_start=yes'))
        files,_=render(self.game,self.mod)
        self.assertIn('user_start=yes',files[ON_ACTIONS]);self.assertNotIn('original_start=yes',files[ON_ACTIONS])

    def test_generated_effect_exits_after_native_technology_and_does_not_stack(self):
        files,report=render(self.game,self.mod);self.assertEqual(report['floors'],{'general':.2,'admiral':.25})
        modifiers=root(files[STATIC]).fields();effect=root(files[SCRIPT]).fields()[EFFECT]
        def apply(native,active):
            active=dict(active)
            for _,action in effect.entries():
                data=action.fields();limit=data['limit'].text();match=re.search(r'has_modifier\s*=\s*(\w+)',limit)
                if match:condition=match[1] in active
                else:
                    match=re.search(r'modifier:country_(general|admiral)_rank_impact_mult\s*<=\s*([0-9.]+)',limit)
                    self.assertIsNotNone(match);role,value=match.groups()
                    contribution=sum(float(modifiers[name].fields().get('country_'+role+'_rank_impact_mult',0)) for name in active)
                    condition=native[role]+contribution<=float(value)
                if condition and 'remove_modifier' in data:active.pop(data['remove_modifier'],None)
                if condition and 'add_modifier' in data:active[data['add_modifier'].fields()['name']]=True
            return active
        state=apply(dict(general=0,admiral=0),{})
        self.assertEqual(set(state),set(MODIFIERS.values()))
        self.assertEqual(apply(dict(general=0,admiral=0),state),state)
        self.assertEqual(apply(dict(general=.2,admiral=0),state),{MODIFIERS['admiral']:True})
        self.assertEqual(apply(dict(general=.6,admiral=.5),state),{})
        self.assertNotIn('add_technology_researched',''.join(files.values()))

    def test_unsupported_technology_rules_fail_instead_of_guessing(self):
        (self.game/'common/technology/technologies/military.txt').write_text('early={modifier={country_general_rank_impact_mult=0.2}}')
        with self.assertRaisesRegex(ValueError,'基准'):render(self.game,self.mod)

    def test_game_technologies_can_contain_multiple_modifier_blocks(self):
        path=self.game/'common/technology/technologies/military.txt'
        path.write_text(path.read_text()+' repeat={modifier={unrelated=1} modifier={country_general_rank_impact_mult=0.6}}')
        _,report=render(self.game,self.mod)
        self.assertEqual(report['floors']['general'],.2)


if __name__=='__main__':unittest.main()
