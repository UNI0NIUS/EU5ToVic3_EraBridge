import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from economy_fleets import BUILDING, convert, verify
from economy_naval_source import prepare
from extract_naval_source import extract
from pdx_text import root
import test_economy_fleets as fleet_fixtures


class NavalSourceTests(unittest.TestCase):
    def setUp(self):
        fleet_fixtures.FleetTests.setUp(self)
        target=self.ledger.target
        target.buildings={BUILDING:root('unlocking_technologies={admiralty}').fields()}
        target.techs={'admiralty':{'unlocking_technologies':root('navigation')},'navigation':{},'drydocks':{}}
        (target.game/'common/ship_types/test.txt').write_text('''ship_type_ship_of_the_line={modifier={ship_crew_max_add=800} unlocking_technologies={drydocks}}
            ship_type_frigate={modifier={ship_crew_max_add=200} unlocking_technologies={navigation}}''')
        self.source={'source_sha256':'abc','locations':{'1':{'name':'port'}}}
        self.political={'source_sha256':'abc','countries':{'X':{'source_id':10}}}
        self.links={'port':{('A','X'):1,('D','Y'):9}}
        self.ledger.techs['X']=set()

    def ship(self,uid,category,owner='10'):
        return {'id':uid,'type':'old_'+category,'category':category,'owner':owner,'home':'1','last_port':'1','hulls':1}

    def test_source_counts_replace_template_even_when_old_fleet_is_empty(self):
        naval={'source_sha256':'abc','ships':[self.ship('1','navy_heavy_ship'),self.ship('2','navy_galley'),self.ship('3','navy_light_ship'),self.ship('4','navy_transport')],'excluded':[]}
        ships,audit=prepare(self.ledger,self.source,naval,self.political,self.links)
        self.assertEqual(len(ships['X']),3)
        self.assertEqual(audit['countries']['X']['source_transports'],1)
        self.assertEqual(audit['countries']['X']['transports'][0]['id'],'4')
        self.assertEqual(ships['X'][0]['home_weights'],{'A':1})
        self.assertEqual(self.ledger.techs['X'],{'admiralty','navigation','drydocks'})
        text,report=convert(self.ledger,'MILITARY_FORMATIONS={c:X ?={}}',{'X'},self.classes,self.policy,ships)
        verify(self.ledger,text,report)
        self.assertEqual(report['countries']['X']['exported_types'],{'ship_type_ship_of_the_line':1,'ship_type_frigate':2})
        self.assertEqual({s for f in report['formations'] for s in f['source_ids']},{'1','2','3'})

    def test_zero_source_navy_does_not_keep_template_ships(self):
        naval={'source_sha256':'abc','ships':[self.ship('1','navy_transport')],'excluded':[]}
        ships,audit=prepare(self.ledger,self.source,naval,self.political,self.links)
        text,report=convert(self.ledger,'MILITARY_FORMATIONS={c:X ?={create_military_formation={type=fleet hq_region=sr:west ship={type=ship_type:ship_type_frigate count=20}}}}',{'X'},self.classes,self.policy,ships)
        verify(self.ledger,text,report)
        self.assertEqual(report['countries']['X']['exported_ships'],0)
        self.assertEqual(self.ledger.techs['X'],set())

    def test_missing_owner_duplicate_hulls_and_source_mismatch(self):
        row=self.ship('1','navy_heavy_ship','unmapped')
        naval={'source_sha256':'abc','ships':[row],'excluded':[]}
        ships,audit=prepare(self.ledger,self.source,naval,self.political,self.links)
        self.assertEqual(audit['unmapped_owner_ships'],[row])
        naval['ships'].append(row)
        with self.assertRaises(ValueError):prepare(self.ledger,self.source,naval,self.political,self.links)
        naval['ships']=[row];naval['source_sha256']='different'
        with self.assertRaises(ValueError):prepare(self.ledger,self.source,naval,self.political,self.links)

    def test_extractor_counts_damaged_hulls_not_strength_or_templates(self):
        with TemporaryDirectory() as directory:
            base=Path(directory);defs=base/'in_game/common/unit_types';defs.mkdir(parents=True)
            (defs/'units.txt').write_text('heavy={category=navy_heavy_ship} inherited={copy_from=heavy} transport={category=navy_transport}')
            save=base/'sample.eu5';save.write_text('''unit_manager={database={10={country=1 last_port=5}}}
            unit_template_manager={database={1={units={inherited=999}}}}
            subunit_manager={database={1={owner=1 unit=10 type=inherited strength=0.01 number=99}
            2={owner=1 unit=10 type=inherited} 3={owner=1 unit=10 type=transport}
            4={owner=1 unit=10 type=inherited mercenary=42} 5={owner=1 unit=10 type=inherited prisoner=yes}}}''')
            output=base/'ships.json';extract(save,base,output)
            report=json.loads(output.read_text());self.assertEqual(len(report['ships']),3)
            self.assertEqual([s['hulls'] for s in report['ships']],[1,1,1])
            self.assertEqual({s['reason'] for s in report['excluded']},{'mercenary','prisoner'})


if __name__=='__main__':unittest.main()
