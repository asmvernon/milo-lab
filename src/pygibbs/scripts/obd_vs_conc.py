import numpy as np
import matplotlib.pyplot as plt
import logging
from pygibbs.kegg_parser import ParsedKeggFile
from pygibbs.pathway import PathwayData
from toolbox.html_writer import HtmlWriter, NullHtmlWriter
from pygibbs.obd_dual import KeggPathway
from pygibbs.thermodynamic_estimators import LoadAllEstimators
from pygibbs.thermodynamic_constants import R, symbol_dr_G_prime 
from argparse import ArgumentParser
import csv
from toolbox import color, util
from collections import defaultdict
from xlwt import Workbook
import types

def ParseConcentrationRange(conc_range):
    (start, step, end) = [float(x) for x in conc_range.split(':')]
    return np.arange(start, end + 1e-10, step)

def KeggFile2PathwayList(pathway_file):
    kegg_file = ParsedKeggFile.FromKeggFile(pathway_file)
    entries = kegg_file.entries()
    pathway_list = []
    for entry in entries:
        p_data = PathwayData.FromFieldMap(kegg_file[entry])
        pathway_list.append((entry, p_data))
    return pathway_list

def GetAllOBDs(pathway_list, html_writer, thermo, pH=None,
               plot_profile=False, section_prefix="", balance_water=True,
               override_bounds={}):
    """
        Return value is a list or dictionaries containing the following fields:
        
            entry         - the name of the pathway
            remark        - typically the exception message if something went wrong
            OBD           - optimized distributed bottleneck (in kJ/mol)
            FFE           - flux-force efficiency (between -1 and 1)
            min total dG  - in kJ/mol
            max total dG  - in kJ/mol
            sum of fluxes - the sum of all fluxes
    """
    if html_writer is None:
        html_writer = NullHtmlWriter()
    
    html_writer.write('<h2 id="%s_tables">Individual result tables</h1>\n' % section_prefix)
    rowdicts = []
    for entry, p_data in pathway_list:
        rowdict = defaultdict(float) 
        rowdicts.append(rowdict)
        rowdict['entry'] = entry
        rowdict['remark'] = 'okay'

        if p_data.skip:
            logging.info("Skipping pathway: %s", rowdict['entry'])
            rowdict['remark'] = 'skipping'
            continue
        
        if pH is None:
            pH = p_data.pH
        thermo.SetConditions(pH=pH, I=p_data.I, T=p_data.T, pMg=p_data.pMg)
        thermo.c_range = p_data.c_range
        rowdict['pH'] = thermo.pH
        rowdict['I'] = thermo.I
        rowdict['T'] = thermo.T
        rowdict['pMg'] = thermo.pMg

        #html_writer.write('<a name="%s"></a>\n' % entry)
        html_writer.write('<h3 id="%s_%s">%s</h2>\n' % (section_prefix, rowdict['entry'], rowdict['entry']))

        S, rids, fluxes, cids = p_data.get_explicit_reactions(balance_water=balance_water)
        fluxes = np.matrix(fluxes)
        rowdict['rids'] = rids
        rowdict['cids'] = cids
        rowdict['fluxes'] = fluxes

        thermo.bounds = p_data.GetBounds().GetOldStyleBounds(cids)
        for cid, (lb, ub) in override_bounds.iteritems():
            thermo.bounds[cid] = (lb, ub)
        
        dG0_r_prime = thermo.GetTransfromedReactionEnergies(S, cids)
        rowdict['dG0_r_prime'] = dG0_r_prime
        
        keggpath = KeggPathway(S, rids, fluxes, cids, reaction_energies=dG0_r_prime,
                               cid2bounds=thermo.bounds, c_range=thermo.c_range)
        rowdict['formulas'] = [keggpath.GetReactionString(r, show_cids=False)
                               for r in xrange(len(rids))]

        if np.any(np.isnan(dG0_r_prime)):
            html_writer.write('NaN reaction energy')
            keggpath.WriteProfileToHtmlTable(html_writer)
            keggpath.WriteConcentrationsToHtmlTable(html_writer)
            logging.info('%20s: OBD = NaN, maxTG = NaN' % (entry))
            rowdict['remark'] = 'NaN reaction energy'
            continue

        obd, params = keggpath.FindOBD()
        odfe = 100 * np.tanh(obd / (2*R*thermo.T))

        rowdict['OBD'] = obd
        rowdict['FFE'] = odfe
        rowdict['sum of fluxes'] = np.sum(fluxes)
        rowdict['concentrations'] = params['concentrations']
        rowdict['reaction prices'] = params['reaction prices']
        rowdict['compound prices'] = params['compound prices']
        rowdict['min total dG'] = params['minimum total dG']
        rowdict['max total dG'] = params['maximum total dG']

        logging.info('%20s: OBD = %.1f [kJ/mol], maxTG = %.1f [kJ/mol]' %
                     (rowdict['entry'], obd, rowdict['max total dG']))
        html_writer.write_ul(["pH = %.1f, I = %.2fM, T = %.2f K" % (thermo.pH, thermo.I, thermo.T),
                              "OBD = %.1f [kJ/mol]" % obd,
                              "flux-force efficiency = %.1f%%" % odfe,
                              "Min Total %s = %.1f [kJ/mol]" % (symbol_dr_G_prime, rowdict['min total dG']),
                              "Max Total %s = %.1f [kJ/mol]" % (symbol_dr_G_prime, rowdict['max total dG'])])
        rowdict['dG_r_prime'] = keggpath.CalculateReactionEnergiesUsingConcentrations(rowdict['concentrations'])
        keggpath.WriteResultsToHtmlTables(html_writer, rowdict['concentrations'],
            rowdict['reaction prices'], rowdict['compound prices'])
        
    html_writer.write('<h2 id="%s_summary">Summary table</h1>\n' % section_prefix)
    dict_list = [{'Name':'<a href="#%s_%s">%s</a>' % (section_prefix, d['entry'], d['entry']),
                  'OBD [kJ/mol]':'%.1f' % d['OBD'],
                  'flux-force eff.':'%.1f%%' % d['FFE'],
                  'Total dG\' [kJ/mol]':'%6.1f - %6.1f' % (d['min total dG'], d['max total dG']),
                  'sum(flux)':'%g' % d['sum of fluxes'],
                  'remark': d['remark']}
                 for d in rowdicts]
    html_writer.write_table(dict_list,
        headers=['Name', 'OBD [kJ/mol]', 'flux-force eff.', 'Total dG\' [kJ/mol]', 'sum(flux)', 'remark'])

    return rowdicts

def AnalyzePareto(pathway_file, output_prefix, thermo, pH=None):
    pathway_list = KeggFile2PathwayList(pathway_file)
    pathway_names = [entry for (entry, _) in pathway_list]
    html_writer = HtmlWriter('%s.html' % output_prefix)
    xls_workbook = Workbook()

    logging.info("running OBD analysis for all pathways")
    data = GetAllOBDs(pathway_list, html_writer, thermo,
                  pH=pH, section_prefix="pareto", balance_water=True,
                  override_bounds={})
    
    for d in data:
        sheet = xls_workbook.add_sheet(d['entry'])
        sheet.write(0, 0, "reaction")
        sheet.write(0, 1, "formula")
        sheet.write(0, 2, "flux")
        sheet.write(0, 3, "delta_r G'")
        sheet.write(0, 4, "shadow price")
        for r, rid in enumerate(d['rids']):
            sheet.write(r+1, 0, rid)
            sheet.write(r+1, 1, d['formulas'][r])
            sheet.write(r+1, 2, d['fluxes'][0, r])
            sheet.write(r+1, 3, d['dG_r_prime'][0, r])
            sheet.write(r+1, 4, d['reaction prices'][r, 0])
    
    xls_workbook.save('%s.xls' % output_prefix)

    obds = []
    minus_avg_tg = []
    for i, d in enumerate(data):
        obds.append(d['OBD'])
        if d['sum of fluxes']:
            minus_avg_tg.append(-d['max total dG']/d['sum of fluxes'])
        else:
            minus_avg_tg.append(0)
            
    fig = plt.figure(figsize=(6, 6), dpi=90)
    plt.plot(minus_avg_tg, obds, 'o', figure=fig)
    plt.plot([0, max(minus_avg_tg)], [0, max(minus_avg_tg)], '--g')
    for i, name in enumerate(pathway_names):
        plt.text(minus_avg_tg[i], obds[i], name)
    plt.title('OBD vs. Average $\Delta_r G$')
    plt.ylim(ymin=0)
    plt.xlim(xmin=0)
    plt.xlabel(r'- Average $\Delta_r G$ [kJ/mol]')
    plt.ylabel(r'Optimized Distributed Bottleneck [kJ/mol]')
    html_writer.write('<h2>Pareto figure</h1>\n')
    html_writer.embed_matplotlib_figure(fig)
    html_writer.close()
            
def AnalyzeConcentrationGradient(pathway_file, output_prefix, thermo, conc_range, cids=[], pH=None):
    compound_names = ','.join([thermo.kegg.cid2name(cid) for cid in cids])
    pathway_list = KeggFile2PathwayList(pathway_file)
    pathway_names = [entry for (entry, _) in pathway_list]
    html_writer = HtmlWriter('%s.html' % output_prefix)
    
    # run once just to make sure that the pathways are all working:
    logging.info("testing all pathways with default concentrations")
    data = GetAllOBDs(pathway_list, html_writer, thermo,
                  pH=pH, section_prefix="test", balance_water=True,
                  override_bounds={})
    
    csv_output = csv.writer(open('%s.csv' % output_prefix, 'w'))
    csv_output.writerow(['pH', '[' + compound_names + ']'] + pathway_names)

    conc_vec = 10**(-ParseConcentrationRange(conc_range)) # logarithmic scale between 10mM and 1nM
    override_bounds = {}
    
    obd_mat = []
    for conc in conc_vec.flat:
        for cid in cids:
            override_bounds[cid] = (conc, conc)
        logging.info("[%s] = %.1e M" % (compound_names, conc))
        data = GetAllOBDs(pathway_list, html_writer=None, thermo=thermo,
                      pH=pH, section_prefix="", balance_water=True,
                      override_bounds=override_bounds)
        obds = [d['OBD'] for d in data]
        obd_mat.append(obds)
        csv_output.writerow([data[0]['pH'], conc] + obds)
    obd_mat = np.matrix(obd_mat) # rows are pathways and columns are concentrations

    fig = plt.figure(figsize=(6, 6), dpi=90)
    colormap = color.ColorMap(pathway_names)
    for i, name in enumerate(pathway_names):
        plt.plot(conc_vec, obd_mat[:, i], '-', color=colormap[name], 
                 figure=fig)
    plt.title("OBD vs. [%s]" % (compound_names), figure=fig)
    plt.xscale('log')
    plt.ylim(ymin=0)
    plt.xlabel('[%s] (in M)' % compound_names, figure=fig)
    plt.ylabel('Optimized Distributed Bottleneck [kJ/mol]', figure=fig)
    plt.legend(pathway_names)
    html_writer.write('<h2>Summary figure</h1>\n')
    html_writer.embed_matplotlib_figure(fig)
    html_writer.close()

def AnalyzePHGradient(pathway_file, output_prefix, thermo, conc_range):
    pathway_list = KeggFile2PathwayList(pathway_file)
    pathway_names = [entry for (entry, _) in pathway_list]
    html_writer = HtmlWriter('%s.html' % output_prefix)
    
    # run once just to make sure that the pathways are all working:
    logging.info("testing all pathways with default pH")
    data = GetAllOBDs(pathway_list, html_writer, thermo,
                  pH=None, section_prefix="test", balance_water=True,
                  override_bounds={})
    
    csv_output = csv.writer(open('%s.csv' % output_prefix, 'w'))
    csv_output.writerow(['pH'] + pathway_names)
    
    util._mkdir(output_prefix)
    shadow_csvs = {}
    for d in data:
        path = '%s/%s.csv' % (output_prefix, d['entry'])
        shadow_csvs[d['entry']] = csv.writer(open(path, 'w'))
        shadow_csvs[d['entry']].writerow(['pH'] + d['rids'])

    pH_vec = ParseConcentrationRange(conc_range)
    obd_mat = []
    for pH in pH_vec.flat:
        logging.info("pH = %.1f" % (pH))
        data = GetAllOBDs(pathway_list, html_writer=None, thermo=thermo,
                      pH=pH, section_prefix="", balance_water=True,
                      override_bounds={})
        obds = [d['OBD'] for d in data]
        obd_mat.append(obds)
        csv_output.writerow([data[0]['pH']] + obds)
        
        for d in data:
            if type(d['reaction prices']) != types.FloatType:
                prices = list(d['reaction prices'].flat)
                shadow_csvs[d['entry']].writerow([pH] + prices)
            
    obd_mat = np.matrix(obd_mat) # rows are pathways and columns are concentrations

    fig = plt.figure(figsize=(6, 6), dpi=90)
    colormap = color.ColorMap(pathway_names)
    for i, name in enumerate(pathway_names):
        plt.plot(pH_vec, obd_mat[:, i], '-', color=colormap[name], 
                 figure=fig)
    plt.title("OBD vs. pH", figure=fig)
    plt.ylim(0, np.max(obd_mat.flat))
    plt.xlabel('pH', figure=fig)
    plt.ylabel('Optimized Distributed Bottleneck [kJ/mol]', figure=fig)
    plt.legend(pathway_names)
    html_writer.write('<h2>Summary figure</h1>\n')
    html_writer.embed_matplotlib_figure(fig)
    
    html_writer.close()

def MakeArgParser(estimators):
    """Returns an OptionParser object with all the default options."""
    parser = ArgumentParser(description='A script for running OBD analysis for a gradient of concentrations')
    parser.add_argument('-i', '--pathway_file', action='store', type=file, required=True, 
                        help="input pathway description file in KEGG format")
    parser.add_argument('-o', '--output_prefix', action='store', required=False,
                        default='../res/obd_analysis',
                        help='the prefix for the output files (*.html and *.csv)')
    parser.add_argument('-c', '--cids', action='append', type=int, required=False,
                        default=None,
                        help='an integer for the accumulator')
    parser.add_argument('-r', '--range', action='store', required=False,
                        default=None)
    parser.add_argument('-s', '--thermodynamics_source', action='store', required=False,
                        choices=estimators.keys(),
                        default="UGC",
                        help="The thermodynamic data to use")
    parser.add_argument('-p', '--pH', action='store', type=float, required=False,
                        default=None,
                        help="Override the pH indicated in the pathway file")
    return parser

if __name__ == "__main__":
    estimators = LoadAllEstimators()
    parser = MakeArgParser(estimators)
    args = parser.parse_args()

    plt.rcParams['legend.fontsize'] = 6
    thermo = estimators[args.thermodynamics_source]

    if not args.cids:
        AnalyzePareto(args.pathway_file, args.output_prefix, thermo, pH=args.pH)  
    elif 80 in args.cids:
        if args.range is None:
            args.range = '4:0.5:10'
        AnalyzePHGradient(args.pathway_file, args.output_prefix, thermo,
                          conc_range=args.range)
    else:
        if args.range is None:
            args.range = '2:0.5:6'
        AnalyzeConcentrationGradient(args.pathway_file, args.output_prefix, thermo,
                                     conc_range=args.range, cids=args.cids, pH=args.pH)

