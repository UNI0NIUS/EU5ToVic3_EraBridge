import tempfile
import unittest
from pathlib import Path
from v3_startup_validation import rewrite_homelands, validate_state_history, culture_modifiers, flag_assets, MODIFIER_KINDS


class StartupValidationTests(unittest.TestCase):
    def test_homeland_replacement_consumes_scoped_token_and_preserves_ownership(self):
        content = 'STATES = { s:STATE_A = { create_state = { country = c:AAA owned_provinces = { x123456 } } add_homeland = cu:old } }'
        changed = rewrite_homelands(content, {'STATE_A': {'new'}})
        self.assertNotIn('old', changed)
        self.assertIn('country = c:AAA owned_provinces = { x123456 }', changed)
        self.assertIn('add_homeland = cu:new', changed)
        self.assertEqual(validate_state_history(changed, {'new'}), 1)
        self.assertEqual(rewrite_homelands(changed, {'STATE_A': {'new'}}), changed)

    def test_verifier_rejects_actual_test1_failure_modes(self):
        for body in (':old add_homeland = cu:new', 'add_homeland = new', 'add_homeland = cu:missing'):
            with self.subTest(body=body), self.assertRaises(ValueError):
                validate_state_history('STATES = { s:STATE_A = { ' + body + ' } }', {'new'})
        with self.assertRaises(ValueError):
            rewrite_homelands('STATES = { s:STATE_A = { :old } }', {})

    def test_custom_culture_requires_all_six_vanilla_compatible_definitions(self):
        with tempfile.TemporaryDirectory() as tmp:
            game, mod = Path(tmp)/'game', Path(tmp)/'mod'
            for base in (game, mod):
                (base/'common/cultures').mkdir(parents=True)
                (base/'common/static_modifiers').mkdir()
                (base/'common/modifier_type_definitions').mkdir()
            (game/'common/cultures/base.txt').write_text('scottish = { }')
            (mod/'common/cultures/custom.txt').write_text('custom = { }')
            template = ''.join(f'scottish_{kind}_modifier_{sign} = {{ {effect.format(culture="scottish")} = 1 }}\n'
                               for kind, effect in MODIFIER_KINDS.items() for sign in ('positive', 'negative'))
            (game/'common/static_modifiers/base.txt').write_text(template)
            (game/'common/modifier_type_definitions/base.txt').write_text(''.join(effect.format(culture='scottish')+' = { decimals = 1 color = good game_data = { ai_value = 0 } }\n' for effect in MODIFIER_KINDS.values()))
            with self.assertRaises(ValueError): culture_modifiers(game, mod)
            self.assertEqual(culture_modifiers(game, mod, write=True), 6)
            self.assertEqual(culture_modifiers(game, mod), 12)
            self.assertEqual(culture_modifiers(game, mod, write=True), 6)
            from v3_startup_validation import MODIFIER_TYPES_FILE
            (mod/MODIFIER_TYPES_FILE).unlink()
            with self.assertRaisesRegex(ValueError, 'modifier type'):
                culture_modifiers(game, mod)

    def test_religion_dependencies_are_generated_from_vanilla_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            game, mod = Path(tmp)/'game', Path(tmp)/'mod'
            for base in (game,mod):
                for category in ('religions','static_modifiers','modifier_type_definitions'):
                    (base/'common'/category).mkdir(parents=True)
            (game/'common/religions/base.txt').write_text('catholic = { }')
            (mod/'common/religions/custom.txt').write_text('custom_faith = { }')
            (game/'common/static_modifiers/base.txt').write_text(''.join('catholic_standard_of_living_modifier_'+sign+' = { state_catholic_standard_of_living_add = 1 }\n' for sign in ('positive','negative')))
            (game/'common/modifier_type_definitions/base.txt').write_text('state_catholic_standard_of_living_add = { decimals = 1 color = good }')
            self.assertEqual(culture_modifiers(game,mod,write=True),2)
            self.assertEqual(culture_modifiers(game,mod),4)

    def test_flag_validation_checks_context_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            game, mod, eu5 = (Path(tmp)/x for x in ('game', 'mod', 'eu5'))
            (mod/'common/coat_of_arms/coat_of_arms').mkdir(parents=True)
            (mod/'common/coat_of_arms/coat_of_arms/test.txt').write_text('flag = { colored_emblem = { texture = "eu5_m3_test.dds" } }')
            (eu5/'main_menu/gfx/coat_of_arms/textured_emblems').mkdir(parents=True)
            (eu5/'main_menu/gfx/coat_of_arms/textured_emblems/test.dds').write_bytes(b'test texture')
            with self.assertRaises(ValueError): flag_assets(game, mod)
            self.assertEqual(len(flag_assets(game, mod, eu5)), 1)
            self.assertEqual(flag_assets(game, mod), [])


if __name__ == '__main__': unittest.main()
