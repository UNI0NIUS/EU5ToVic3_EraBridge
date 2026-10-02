import unittest
from converter_identity_policy import clean_label,dated_mapping,homelands


class IdentityPolicyTests(unittest.TestCase):
    def test_workflow_label_only(self):
        self.assertEqual(clean_label('傈僳语（审查映射）'),'傈僳语')
        self.assertEqual(clean_label('Lisu language (reviewed mapping)'),'Lisu language')
        self.assertEqual(clean_label('提格雷（Tigre）'),'提格雷（Tigre）')

    def test_date_sensitive_identity_does_not_mutate_base(self):
        m={'lozi':'luyi'};p={'dated_mappings':{'lozi':{'from_year':1830,'target':'lozi'}}}
        self.assertEqual(dated_mapping(m,p,'1780.1.1')['lozi'],'luyi')
        self.assertEqual(dated_mapping(m,p,'1836.1.1')['lozi'],'lozi')
        self.assertEqual(m,{'lozi':'luyi'})

    def test_historical_core_and_migrant_majority_not_owner_majority(self):
        pops={('S','A','eu5_migrant_a','r'):40,('S','B','ordinary','r'):60,('T','A','eu5_migrant_a','r'):51,('T','A','ordinary','r'):49,('U','A','eu5_migrant_a','r'):50,('U','B','ordinary','r'):50}
        history={'entries':[{'culture':'ordinary','status':'candidate_core','states':['S','T'],'anchors':{'core':['S']}},{'culture':'deferred','status':'deferred','states':['S'],'anchors':{'core':['S']}}]}
        src=[{'location':'core','source_culture':'src','centipersons':'1'}]
        home,reasons=homelands(history,pops,src,{'src':'ordinary'},{'core':['p','q']},{'p':('S','A'),'q':('T','A')},{'S':{'indigenous'}})
        self.assertEqual(home['S'],{'indigenous','ordinary'})
        self.assertEqual(home['T'],{'eu5_migrant_a'})
        self.assertFalse(home['U'])
        absent,_=homelands(history,pops,[],{'src':'ordinary'},{'core':['p']},{'p':('S','A')},{})
        self.assertNotIn('ordinary',absent['S'])


if __name__=='__main__':unittest.main()
