#!/usr/bin/python

import csv
import logging
import pybel
import pylab
import sys

from toolbox import util


class GroupDecompositionError(Exception):
    pass


class GroupsDataError(Exception):
    pass


class MalformedGroupDefinitionError(GroupsDataError):
    pass


class GroupsData(object):
    """Contains data about all groups."""
    
    # Phosphate groups need special treatment, so they are defined in code...
    # TODO(flamholz): Define them in the groups file.
    INITIAL_P_1 = ("-OPO3-", 1, 0)
    INITIAL_P_2 = ("-OPO3-", 0, -1)
    MIDDLE_P_1 = ("-OPO2-", 1, 0)
    MIDDLE_P_2 = ("-OPO2-", 0, -1)
    FINAL_P_1 = ("-OPO3", 1, -1)
    FINAL_P_2 = ("-OPO3", 0, -2)
    #FINAL_P_3 = ("-OPO3",  2,  0)
    
    DEFAULT_INTERIOR_P = MIDDLE_P_2  # Ignoring protonation, interior chain
    DEFAULT_EXTERIOR_P = FINAL_P_1   # Ignoring protonation, exterior chain
    
    PHOSPHATE_GROUPS = (
        INITIAL_P_1, INITIAL_P_2,
        MIDDLE_P_1, MIDDLE_P_2,
        FINAL_P_1, FINAL_P_2)
    
    def __init__(self, groups):
        """Construct GroupsData.
        
        Args:
            groups: a list of group tuples, read from CSV.
        """
        self.groups = groups
        self.all_groups = self._GetAllGroups(self.groups) 
        self.all_group_names = ['%s [H%d %d]' % (group_name, protons, charge) for (group_name, protons, charge) in self.all_groups]
        self.all_group_hydrogens = pylab.array([protons for (group_name, protons, charge) in self.all_groups])
        self.all_group_charges = pylab.array([charge for (group_name, protons, charge) in self.all_groups])
    
    @staticmethod
    def IsPhosphate(group_name):
        return group_name.startswith('*P')
    
    @staticmethod
    def IgnoreCharges(group_name):
        # (I)gnore charges
        return group_name[2] == 'I'
    
    @staticmethod
    def ChargeSensitive(group_name):
        # (C)harge sensitive
        return group_name[2] == 'C'
    
    @staticmethod
    def _GetAllGroups(groups):
        all_groups = []
        
        for _, group_name, protons, charge, _, _ in groups:
            # Expand phosphate groups.
            if GroupsData.IsPhosphate(group_name):
                all_groups.extend(GroupsData.PHOSPHATE_GROUPS)
            else:
                all_groups.append((group_name, protons, charge))
        
        # Add the origin.
        all_groups.append(('origin', 0, 0))
        return all_groups
    
    @staticmethod
    def _ConvertFocalAtoms(focal_atoms_str):
        return [int(c) for c in focal_atoms_str.split('|')]
    
    @staticmethod
    def FromGroupsFile(filename):
        """Factory that initializes a GroupData from a CSV file."""
        assert filename
        list_of_groups = []
        
        logging.info('Reading the list of groups from %s ... ' % filename)
        group_csv_file = csv.reader(open(filename, 'r'))
        group_csv_file.next() # Skip the header
    
        gid = 0
        for row in group_csv_file:
            try:
                (group_name, protons, charge, smarts, focal_atoms, remark) = row
                
                if focal_atoms:
                    focal_atoms = GroupsData._ConvertFocalAtoms(focal_atoms)
                if protons:
                    protons = int(protons)
                if charge:
                    charge = int(charge)
                
                # Check that the smarts are good.
                pybel.Smarts(smarts)
                
                list_of_groups.append((gid, group_name, protons, charge, str(smarts), focal_atoms))
            except ValueError, msg:
                print msg
                raise GroupsDataError('Wrong number of columns (%d) in one of the rows in %s: %s' %
                                      (len(row), filename, str(row)))
            except IOError:
                raise GroupsDataError('Cannot parse SMARTS from line %d: %s' %
                                      (group_csv_file.line_num, smarts))
            
            gid += 1
        logging.info('Done reading groups data.')
        
        return GroupsData(list_of_groups)    

    @staticmethod
    def FromDatabase(db_comm):
        """Factory that initializes a GroupData from a DB connection."""
        logging.info('Reading the list of groups from the database.')
        
        list_of_groups = []
        for row in db_comm.execute("SELECT * FROM groups"):
            (gid, group_name, protons, charge, smarts, focal_atom_set, remark) = row
            
            if (focal_atom_set != ""): # otherwise, consider all the atoms as focal atoms
                focal_atoms = set([int(i) for i in focal_atom_set.split('|')])
            else:
                focal_atoms = None

            list_of_groups.append((gid, group_name, protons,
                                   charge, str(smarts), focal_atoms))
        logging.info('Done reading groups data.')
        
        return GroupsData(list_of_groups)
    
    def ToDatabase(self, db_comm):
        """Write the GroupsData to the database."""
        logging.info('Writing GroupsData to the database.')
        
        db_comm.execute('DROP TABLE IF EXISTS groups;')
        db_comm.execute('CREATE TABLE groups (gid INT, name TEXT, protons INT, charge INT, smarts TEXT, focal_atoms TEXT, remark TEXT)')    
        for gid, group_name, protons, charge, smarts, focal_atom_set in self.groups:
            focal_atom_str = '|'.join([str(fa) for fa in focal_atom_set])
            
            db_comm.execute('INSERT INTO groups VALUES(?,?,?,?,?,?,?)', (gid, group_name, int(protons), int(charge),
                                                                         smarts, focal_atom_str, ''))

        logging.info('Done writing groups data into database.')
        
        
class GroupVector(list):
    """A vector of groups."""
    
    def __init__(self, groups_data, iterable=None):
        """Construct a vector.
        
        Args:
            groups_data: data about all the groups.
            iterable: data to load in to the vector.
        """
        self.groups_data = groups_data
        
        if iterable:
            self.extend(iterable)
    
    def __str__(self):
        """Return a string representation of this group vector."""
        group_strs = []
        
        for i, name in enumerate(self.groups_data.all_group_names):
            if self[i]:
                group_strs.append('%s x %d' % (name, self[i]))
        return " | ".join(group_strs)
    
    def NetCharge(self):
        """Returns the net charge."""
        return int(pylab.dot(self, self.groups_data.all_group_charges))
    
    def Hydrogens(self):
        """Returns the number of protons."""
        return int(pylab.dot(self, self.groups_data.all_group_hydrogens))


class GroupDecomposition(object):
    """Class representing the group decomposition of a molecule."""
    
    def __init__(self, groups_data, mol, groups, unassigned_nodes):
        self.groups_data = groups_data
        self.mol = mol
        self.groups = groups
        self.unassigned_nodes = unassigned_nodes

    def ToTableString(self):
        """Returns the decomposition as a tabular string."""
        spacer = '-' * 50 + '\n'
        l = ['%30s | %2s | %2s | %s\n' % ("group name", "nH", "z", "nodes"),
             spacer]
                
        for group_name, protons, charge, node_sets in self.groups:
            for n_set in node_sets:
                s = '%30s | %2d | %2d | %s\n' % (group_name, protons, charge,
                                                 ','.join([str(i) for i in n_set]))
                l.append(s)

        if self.unassigned_nodes:
            l.append('\nUnassigned nodes: \n')
            l.append('%10s | %10s | %10s | %10s\n' % ('index', 'atomicnum',
                                                      'valence', 'charge'))
            l.append(spacer)
            
            for i in self.unassigned_nodes:
                a = self.mol.atoms[i]
                l.append('%10d | %10d | %10d | %10d\n' % (i, a.atomicnum,
                                                          a.heavyvalence, a.formalcharge))
        return ''.join(l)

    def __str__(self):
        """Convert the groups to a string."""        
        group_strs = []
        for group_name, protons, charge, node_sets in self.groups:
            if node_sets:
                group_strs.append('%s [H%d %d] x %d' % (group_name, protons, charge, len(node_sets)))
        return " | ".join(group_strs)
    
    def AsVector(self):
        """Return the group in vector format.
        
        Note: self.groups contains an entry for *all possible* groups, which is
        why this function returns consistent values for all compounds.
        """
        group_vec = GroupVector(self.groups_data)
        for gname, ps, charge, node_sets in self.groups:
            group_vec.append(len(node_sets))
        group_vec.append(1) # The origin
        return group_vec
    
    def NetCharge(self):
        """Returns the net charge."""
        return self.AsVector().NetCharge()
    
    def Hydrogens(self):
        """Returns the number of protons."""
        return self.AsVector().Hydrogens()

    def PseudoisomerVectors(self):
        """Returns a list of group vectors, one per pseudo-isomer."""    
        # 'group_name_to_index' is a map from each group name to its indices in the groupvec
        # note that some groups appear more than once (since they can have multiple protonation
        # levels).
        group_name_to_index = {}

        # 'group_name_to_count' is a map from each group name to its number of appearences in 'mol'
        group_name_to_count = {}
        for i, gdata in enumerate(self.groups):
            group_name, protons, charge, node_sets = gdata
            group_name_to_index[group_name] = group_name_to_index.get(group_name, []) + [i]
            group_name_to_count[group_name] = group_name_to_count.get(group_name, 0) + len(node_sets)
        
        index_vector = [] # maps the new indices to the original ones that are used in groupvec

        # a list of pairs, each containing the 'count' of each group and the number of possible protonations.
        total_slots_pairs = [] 

        for group_name in group_name_to_index.keys():
            groupvec_indices = group_name_to_index[group_name]
            index_vector += groupvec_indices
            total_slots_pairs.append((group_name_to_count[group_name], len(groupvec_indices)))

        # generate all possible assignments of protonations. Each group can appear several times, and we
        # can assign a different protonation level to each of the instances.
        groupvec_list = []
        for assignment in util.multi_distribute(total_slots_pairs):
            v = [0] * len(index_vector)
            for i in xrange(len(v)):
                v[index_vector[i]] = assignment[i]
            v += [1]  # add 1 for the 'origin' group
            groupvec_list.append(GroupVector(self.groups_data, v))
        return groupvec_list


class GroupDecomposer(object):
    """Decomposes compounds into their constituent groups."""
    
    def __init__(self, groups_data):
        """Construct a GroupDecomposer.
        
        Args:
            groups_data: a GroupsData object.
        """
        self.groups_data = groups_data

    @staticmethod
    def FromGroupsFile(filename):
        """Factory that initializes a GroupDecomposer from a CSV file."""
        assert filename
        gd = GroupsData.FromGroupsFile(filename)
        return GroupDecomposer(gd)
    
    @staticmethod
    def FromDatabase(db_comm):
        """Factory that initializes a GroupDecomposer from a CSV file."""
        assert db_comm
        gd = GroupsData.FromDatabase(db_comm)
        return GroupDecomposer(gd)
    
    @staticmethod
    def FindSmarts(mol, smarts_str):
        """
        Corrects the pyBel version of Smarts.findall() which returns results as tuples,
        with 1-based indices even though Molecule.atoms is 0-based.

        Args:
            mol: the molecule to search in.
            smarts_str: the SMARTS query to search for.
        
        Returns:
            The re-mapped list of SMARTS matches.
        """
        shift_left = lambda m: [(n - 1) for n in m] 
        return map(shift_left, pybel.Smarts(smarts_str).findall(mol))

    @staticmethod
    def _InternalPChainSmarts(length):
        return ''.join(['CO', 'P(=O)([OH,O-])O' * length, 'C'])
    
    @staticmethod
    def _TerminalPChainSmarts(length):
        return ''.join(['[OH,O-]', 'P(=O)([OH,O-])O' * length, 'C'])

    @staticmethod
    def FindPhosphateChains(mol, max_length=3, ignore_protonations=False):
        """
        Chain end should be 'OC' for chains that do not really end, but link to carbons.
        Chain end should be '[O-1,OH]' for chains that end in an hydroxyl.
    
        Args:
            mol: the molecule to decompose.
            max_length: the maximum length of a phosphate chain to consider.
            ignore_protonations: whether or not to ignore protonation values.
        
        Returns:
            A list of 2-tuples (phosphate group, # occurrences).
        """
        group_map = dict((pg, []) for pg in GroupsData.PHOSPHATE_GROUPS)
        v_charge = [a.formalcharge for a in mol.atoms]
        
        # For each allowed length
        for length in xrange(1, max_length + 1):
            # Find internal phosphate chains (ones in the middle of the molecule).
            smarts_str = GroupDecomposer._InternalPChainSmarts(length)
            for pchain in GroupDecomposer.FindSmarts(mol, smarts_str):
                if ignore_protonations:
                    group_map[GroupsData.DEFAULT_INTERIOR_P].append(set(pchain[1:6]))
                else:
                    charge = v_charge[pchain[4]]
                    protons = charge + 1
                    group_map[("-OPO3-", protons, charge)].append(set(pchain[1:6]))
                
                for j in xrange(length-1):
                    pg_start = 6 + j*4  # start of the phosphate group
                    node_set = set(pchain[pg_start:(pg_start + 4)])
                    if ignore_protonations:
                        group_map[GroupsData.DEFAULT_INTERIOR_P].append(node_set)
                    else:
                        charge = v_charge[pchain[pg_start + 2]]
                        protons = charge + 1
                        group_map[("-OPO2-", protons, charge)].append(node_set)
        
            # Find terminal phosphate chains.
            smarts_str = GroupDecomposer._TerminalPChainSmarts(length)
            for pchain in GroupDecomposer.FindSmarts(mol, smarts_str):
                if ignore_protonations:
                    group_map[GroupsData.DEFAULT_EXTERIOR_P].append(set(pchain[0:5]))
                else:
                    charge = v_charge[pchain[0]] + v_charge[pchain[3]]
                    protons = charge + 2
                    group_key = ("-OPO3", protons, charge)
                    if group_key not in group_map:
                        logging.warning('This protonation (%d) level is not allowed for terminal phosphate groups.' % protons)
                        logging.warning('Assuming the level is actually 1 - i.e. the charge is (-1).')
                        group_map[GroupsData.DEFAULT_EXTERIOR_P].append(set(pchain[0:5]))
                    else:
                        group_map[group_key].append(set(pchain[0:5]))
                        
                for j in xrange(length-1):
                    pg_start = 5 + j*4  # start of the phosphate group
                    node_set = set(pchain[pg_start:(pg_start + 4)])
                    if ignore_protonations:
                        group_map[GroupsData.DEFAULT_INTERIOR_P].append(node_set)
                    else:
                        charge = v_charge[pchain[pg_start + 2]]
                        protons = charge + 1
                        group_map[("-OPO2-", protons, charge)].append(node_set)

        return [(pg, group_map[pg]) for pg in GroupsData.PHOSPHATE_GROUPS]

    def Decompose(self, mol, ignore_protonations=False, strict=False):
        """
        Decompose a molecule into groups.
        
        The flag 'ignore_protonations' should be used when decomposing a compound with lacing protonation
        representation (for example, the KEGG database doesn't posses this information). If this flag is
        set to True, it overrides the '(C)harge sensitive' flag in the groups file (i.e. - *PC)
        
        Args:
            mol: the molecule to decompose.
            ignore_protonations: whether to ignore protonation levels.
            strict: whether to assert that there are no unassigned atoms.
        
        Returns:
            A GroupDecomposition object containing the decomposition.
        """
        unassigned_nodes = set(range(len(mol.atoms)))
        groups = []
        
        for gid, group_name, protons, charge, smarts_str, focal_atoms in self.groups_data.groups:
            # Phosphate chains require a special treatment
            if GroupsData.IsPhosphate(group_name):
                pchain_groups = None
                if GroupsData.IgnoreCharges(group_name) or ignore_protonations:
                    pchain_groups = self.FindPhosphateChains(mol, ignore_protonations=True)
                elif GroupsData.ChargeSensitive(group_name):
                    pchain_groups = self.FindPhosphateChains(mol, ignore_protonations=False)
                else:
                    raise MalformedGroupDefinitionError(
                        'Unrecognized phosphate wildcard: %s' % group_name)
                
                for group_key, group_nodesets in pchain_groups:
                    group_name, protons, charge = group_key
                    current_groups = []
                    
                    for focal_set in group_nodesets:
                        if focal_set.issubset(unassigned_nodes):
                            # Check that the focal-set doesn't override an assigned node
                            current_groups.append(focal_set)
                            unassigned_nodes = unassigned_nodes - focal_set
                    groups.append((group_name, protons, charge, current_groups))
                    
            else:  # Not a phosphate group
                current_groups = []
                for nodes in self.FindSmarts(mol, smarts_str):
                    try:
                        if focal_atoms:
                            focal_set = set([nodes[i] for i in focal_atoms])
                        else:
                            focal_set = set(nodes)
                    except IndexError:
                        logging.error('Focal set for group %s is out of range: %s'
                                      % (group_name, str(focal_atoms)))
                        sys.exit(-1)

                    if (focal_set.issubset(unassigned_nodes)): # check that the focal-set doesn't override an assigned node
                        current_groups.append(focal_set)
                        unassigned_nodes = unassigned_nodes - focal_set
                groups.append((group_name, protons, charge, current_groups))
        
        # Ignore the hydrogen atoms when checking which atom is unassigned
        for nodes in self.FindSmarts(mol, '[H]'): 
            unassigned_nodes = unassigned_nodes - set(nodes)
        
        decomposition = GroupDecomposition(self.groups_data, mol,
                                           groups, unassigned_nodes)
        
        if strict and decomposition.unassigned_nodes:
            raise GroupDecompositionError('Unable to decompose %s into groups.\n%s' %
                                          (mol.title, decomposition.ToTableString()))
        
        return decomposition


def main():
    decomposer = GroupDecomposer.FromGroupsFile('../data/thermodynamics/groups_species.csv')
    
    atp = 'C1=NC2=C(C(=N1)N)N=CN2C3C(C(C(O3)COP(=O)(O)OP(=O)(O)OP(=O)(O)O)O)O'
    coa = 'C1C=CN(C=C1C(=O)N)C2C(C(C(O2)COP(=O)(O)OP(=O)(O)OCC3C(C(C(O3)N4C=NC5=C4N=CN=C5N)O)O)O)O'
    glucose = 'C(C1C(C(C(C(O1)O)O)O)O)O'

    smiless = [atp, coa, glucose]
    mols = [pybel.readstring('smiles', s) for s in smiless]

    for mol in mols:    
        decomposition = decomposer.Decompose(mol)
        print decomposition.ToTableString()
        print decomposition.AsVector()
        print 'Net charge', decomposition.NetCharge()
        print 'Hydrogens', decomposition.Hydrogens()
        
        for v in decomposition.PseudoisomerVectors():
            print v


if __name__ == '__main__':
    main()   