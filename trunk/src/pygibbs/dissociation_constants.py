import csv, re, logging
from kegg import Kegg
from toolbox.database import SqliteDatabase
from pygibbs.group_decomposition import GroupDecomposer, GroupsData

class DissociationConstants:
    def __init__(self, db):
        self.kegg = Kegg()
        self.groups_data = GroupsData.FromDatabase(db.comm)
        self.group_decomposer = GroupDecomposer(self.groups_data)
        self.db = db
        self.cid2pKas = {}
    
    def ReadCSV(self, fname):
        """
            Reads the raw data collected from the CRC handbook and tries to map every
            compound name there to a KEGG compound ID.
        """
        csv_reader = csv.reader(open(fname, 'r'))
        csv_reader.next() # skip title row
        
        last_formula = None
        last_name = None
        data = []
        for formula, name, step, T, pKa in csv_reader:
            if (name or formula):
                cid, kegg_name, distance = self.FindCID(formula, name)
                last_formula = formula
                last_name = name
                step = 1
            else:
                name = last_name
                formula = last_formula

            data.append((cid, kegg_name, distance, name, formula, step, T, pKa))
        
        return data
    
    def Formula2AtomBag(self, formula):
        if (formula == None or formula.find("(") != -1 or formula.find(")") != -1 or formula.find("R") != -1):
            raise Exception("non-specific compound formula: " + formula)
        
        atom_bag = {}
        for (atom, count) in re.findall("([A-Z][a-z]*)([0-9]*)", formula):
            if (count == ''):
                count = 1
            else:
                count = int(count)
            atom_bag[atom] = count

        return atom_bag
    
    def FindCID(self, formula, name):
        name = name.strip()
        cid, kegg_name, distance = self.kegg.name2cid(name, cutoff=3)
        if not cid:
            return None, None, None

        atom_bag = self.Formula2AtomBag(formula)
        kegg_atom_bag = self.kegg.cid2atom_bag(cid)
        if (atom_bag != kegg_atom_bag):
            return None, None, None
        else:
            return cid, kegg_name, distance
    
    def WriteCSV(self, fname, data):
        csv_writer = csv.writer(open(fname, 'w'))
        csv_writer.writerow(('CID', 'Kegg name', 'distance', 'original name', 'formula', 'step', 'T', 'pKa'))
        for cid, kegg_name, distance, name, formula, step, T, pKa in data:
            csv_writer.writerow((cid, kegg_name, distance, name, formula, step, T, pKa))

    def MatchCIDs(self):
        data = self.ReadCSV('../data/thermodynamics/pKa.csv')
        self.WriteCSV('../res/pKa.csv', data)
        # Now, the user must go over the output file, fix the problems in it and save it to:
        # ../data/thermodynamics/pKa_with_cids.csv
            
    def LoadValues(self):
        """
            Load the data regarding pKa values according to KEGG compound IDs.
            First attempts to retrieve the data from the DB. If the table doesn't
            exist, it reads it from the CSV file (while caching it in the DB).
        """
        
        if not self.db.DoesTableExist('pKa'):
            csv_reader = csv.reader(open('../data/thermodynamics/pKa_with_cids.csv', 'r'))
            csv_reader.next() # skip title row
    
            self.db.CreateTable('pKa', 'cid INT, step INT, T REAL, pKa REAL')
            for cid,_,_,step,T,pKa in csv_reader:
                if cid:
                    self.db.Insert('pKa', [int(cid), int(step), str(T), float(pKa)])
            
            self.db.Commit()

        for cid, step, T, pKa in self.db.Execute("SELECT * FROM pKa"):
            self.cid2pKas.setdefault(cid, []).append(pKa)
            
    def AnalyseValues(self):
        for cid, pKas in sorted(self.cid2pKas.iteritems()):
            mol = self.kegg.cid2mol(cid)
            decomposition = self.group_decomposer.Decompose(mol, ignore_protonations=True)
            active_groups = self.GetActiveGroups(decomposition)
            print cid, self.kegg.cid2name(cid), pKas, active_groups

    def GetActiveGroups(self, decomposition):
        group_name_to_index = {}

        # 'group_name_to_count' is a map from each group name to its number of appearances in 'mol'
        group_name_to_count = {}
        for i, gdata in enumerate(decomposition.groups):
            group_name, unused_protons, unused_protons, unused_mgs, node_sets = gdata
            group_name_to_index[group_name] = group_name_to_index.get(group_name, []) + [i]
            group_name_to_count[group_name] = group_name_to_count.get(group_name, 0) + len(node_sets)

        active_groups = []
        for (name, indices) in group_name_to_index.iteritems():
            if len(indices) > 1 and group_name_to_count[name] > 0:
                active_groups.append((name, group_name_to_count[name]))
        
        return active_groups
        

if (__name__ == '__main__'):
    dc = DissociationConstants(SqliteDatabase("../res/gibbs.sqlite"))
    dc.LoadValues()
    dc.AnalyseValues()