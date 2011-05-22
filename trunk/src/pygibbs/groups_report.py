from toolbox.database import SqliteDatabase
from toolbox.html_writer import HtmlWriter
from pygibbs.hatzimanikatis import Hatzi
from pygibbs.thermodynamics import PsuedoisomerTableThermodynamics
from toolbox.util import lsum
from pygibbs.thermodynamic_constants import default_I, default_pH, default_pMg,\
    default_T
from pygibbs.kegg import Kegg
from pygibbs.thermodynamic_errors import MissingCompoundFormationEnergy

def main():
    #db_public = SqliteDatabase('../data/public_data.sqlite')
    db_gibbs = SqliteDatabase('../res/gibbs.sqlite')
    html_writer = HtmlWriter("../res/groups_report.html")
    kegg = Kegg.getInstance()
    
    #pH, I, pMg, T = default_pH, default_I, default_pMg, default_T
    pH, I, pMg, T = default_pH, 0, 14, default_T
    
    cid2error = {}
    for row_dict in db_gibbs.DictReader("gc_errors"):
        cid = int(row_dict['cid'])
        cid2error[cid] = row_dict['error']

    estimators = {}
    estimators['hatzi'] = Hatzi(use_pKa=False)
    estimators['milo'] = PsuedoisomerTableThermodynamics.FromDatabase(
        db_gibbs, 'gc_pseudoisomers', name='Milo Group Contribution')
    
    all_cids = set(lsum([e.get_all_cids() for e in estimators.values()]))
    dict_list = []
    for cid in all_cids:
        try:
            name = kegg.cid2name(cid)
            link = kegg.cid2compound(cid).get_link()
        except KeyError:
            name = "unknown"
            link = ""
        row_dict = {'cid':'<a href="%s">C%05d</a>' % (link, cid),
                    'name':name, 'error':cid2error.get(cid, None)}
        for key, est in estimators.iteritems():
            try:
                pmap = est.cid2PseudoisomerMap(cid)
                dG0, dG0_tag, nH, z, nMg = pmap.GetMostAbundantPseudoisomer(pH, I, pMg, T)
            except MissingCompoundFormationEnergy:
                dG0, dG0_tag, nH, z, nMg = "", "", "", "", ""
            row_dict['nH_' + key] = nH
            row_dict['charge_' + key] = z
            row_dict['nMg_' + key] = nMg
            row_dict['dG0_' + key] = dG0
            row_dict['dG0_tag_' + key] = dG0_tag
        dict_list.append(row_dict)
        
    html_writer.write_table(dict_list, headers=['cid', 'name', 'charge_hatzi', 'charge_milo', 'error'])
    html_writer.close()
    
if __name__ == '__main__':
    main()