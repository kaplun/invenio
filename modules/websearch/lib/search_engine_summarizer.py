# -*- coding: utf-8 -*-

## This file is part of Invenio.
## Copyright (C) 2008, 2010, 2011 CERN.
##
## Invenio is free software; you can redistribute it and/or
## modify it under the terms of the GNU General Public License as
## published by the Free Software Foundation; either version 2 of the
## License, or (at your option) any later version.
##
## Invenio is distributed in the hope that it will be useful, but
## WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
## General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Invenio; if not, write to the Free Software Foundation, Inc.,
## 59 Temple Place, Suite 330, Boston, MA 02111-1307, USA.

"""
Search Engine Summarizer, producing summary formats such as citesummary.
The main API is summarize_records().
"""

__lastupdated__ = """$Date$"""

__revision__ = "$Id$"

from invenio.config import CFG_INSPIRE_SITE
from invenio.bibrank_citation_searcher import get_cited_by_list
from invenio.listutils import get_mode, get_median, get_mean
import search_engine
import invenio.template
websearch_templates = invenio.template.load('websearch')

## CFG_CITESUMMARY_COLLECTIONS -- how do we break down cite summary
## results according to collections?
if CFG_INSPIRE_SITE:
    CFG_CITESUMMARY_COLLECTIONS = [['All papers', 'collection:citeable'],
                                   ['Published only', 'collection:published']]
else:
    CFG_CITESUMMARY_COLLECTIONS = [['All papers', ''],
                                   ['Published only', 'collection:article']]

## CFG_CITESUMMARY_FAME_THRESHOLDS -- how do we break down cite
## summary results into famous and less famous paper groups?
CFG_CITESUMMARY_FAME_THRESHOLDS = [
                                   (500, 1000000, 'Renowned papers (500+)'),
                                   (250, 499, 'Famous papers (250-499)'),
                                   (100, 249, 'Very well-known papers (100-249)'),
                                   (50, 99, 'Well-known papers (50-99)'),
                                   (10, 49, 'Known papers (10-49)'),
                                   (1, 9, 'Less known papers (1-9)'),
                                   (0, 0, 'Unknown papers (0)')
                                   ]

def summarize_records(recids, of, ln, searchpattern="", searchfield="", req=None):
    """Write summary report for records RECIDS in the format OF in language LN.
       SEARCHPATTERN and SEARCHFIELD are search query that led to RECIDS,
       for instance p='Smith, Paul' and f='author'.  They are used for links.
       REQ is the Apache/mod_python request object.
    """
    if of == 'hcs':
        # this is HTML cite summary
        html = []
        # 0) hcs narrowing box
        narrowing_box = websearch_templates.tmpl_citesummary_narrowing_box(searchpattern, searchfield, ln)
        if not req:
            html.append(narrowing_box)
        elif hasattr(req, "write"):
            req.write(narrowing_box)

        # 1) hcs prologue:
        d_recids = {}
        d_total_recs = {}
        for coll, colldef in CFG_CITESUMMARY_COLLECTIONS:
            if not colldef:
                d_recids[coll] = recids
            else:
                d_recids[coll] = recids & search_engine.search_pattern(p=colldef)
            d_total_recs[coll] = len(d_recids[coll])

        prologue = websearch_templates.tmpl_citesummary_prologue(d_total_recs, CFG_CITESUMMARY_COLLECTIONS, searchpattern, searchfield, ln)

        if not req:
            html.append(prologue)
        elif hasattr(req, "write"):
            req.write(prologue)

        # 2) hcs overview (and calculations for mean, median, and mode of cites):
        d_recid_citers = {}
        d_total_cites = {}
        d_avg_cites = {}
        d_median_cites = {}
        d_mode_cites = {}
        d_recid_citecount_l = {}
        d_num_citing = {}
        for coll, colldef in CFG_CITESUMMARY_COLLECTIONS:
            d_total_cites[coll] = 0
            d_avg_cites[coll] = 0
            d_median_cites[coll] = 0
            d_mode_cites[coll] = 0
            d_recid_citecount_l[coll] = []
            d_recid_citers[coll] =  get_cited_by_list(d_recids[coll])
            citation_count_list = []
            citing_papers = set()
            for recid, lciters in d_recid_citers[coll]:
                if lciters:
                    citation_count_list.append(len(lciters))
                    d_total_cites[coll] += len(lciters)
                    d_recid_citecount_l[coll].append((recid, len(lciters)))
                    citing_papers |= set(lciters)
                else:
                    citation_count_list.append(0)
            if d_total_cites[coll] != 0:
                d_avg_cites[coll] = get_mean(citation_count_list)
                d_median_cites[coll] = get_median(citation_count_list)
                d_mode_cites[coll] = get_mode(citation_count_list)
            d_num_citing[coll] = len(citing_papers)
        overview = websearch_templates.tmpl_citesummary_overview(d_total_cites,
                                                                 CFG_CITESUMMARY_COLLECTIONS,
                                                                 ln)

        if not req:
            html.append(overview)
        elif hasattr(req, "write"):
            req.write(overview)

        # 3) hcs break down by fame:
        for low, high, fame in CFG_CITESUMMARY_FAME_THRESHOLDS:
            d_cites = {}
            for coll, colldef in CFG_CITESUMMARY_COLLECTIONS:
                d_cites[coll] = 0
                for recid, lciters in d_recid_citers[coll]:
                    numcites = 0
                    if lciters:
                        numcites = len(lciters)
                    if numcites >= low and numcites <= high:
                        d_cites[coll] += 1
            fame_info = websearch_templates.tmpl_citesummary_breakdown_by_fame(d_cites, low, high, fame, CFG_CITESUMMARY_COLLECTIONS, searchpattern, searchfield, ln)

            if not req:
                html.append(fame_info)
            elif hasattr(req, "write"):
                req.write(fame_info)

        # 4) hcs calculate h index
        d_h_factors = {}
        def comparator(x, y):
            if x[1] > y[1]:
                return -1
            elif x[1] == y[1]:
                return 0
            else: return +1
        for coll, colldef in CFG_CITESUMMARY_COLLECTIONS:
            d_h_factors[coll] = 0
            d_recid_citecount_l[coll].sort(cmp=comparator)
            #req.write(repr(d_recid_citecount_l[coll])) # DEBUG
            for citecount in d_recid_citecount_l[coll]:
                d_h_factors[coll] += 1
                if d_h_factors[coll] > citecount[1]:
                    d_h_factors[coll] -= 1
                    break
        additional = websearch_templates.tmpl_citesummary_additional_metrics(d_h_factors,
                                                                             d_num_citing,
                                                                             d_avg_cites,
                                                                             d_median_cites,
                                                                             d_mode_cites,
                                                                             CFG_CITESUMMARY_COLLECTIONS,
                                                                             ln)

        if not req:
            html.append(additional)
        elif hasattr(req, "write"):
            req.write(additional)

        # 5) hcs epilogue:
        epilogue = websearch_templates.tmpl_citesummary_epilogue(ln)

        if not req:
            html.append(epilogue)
        elif hasattr(req, "write"):
            req.write(epilogue)

        if not req:
            return "\n".join(html)
        else:
            return ''

    elif of == 'xcs':
        # this is XML cite summary
        citedbylist = get_cited_by_list(recids)
        return print_citation_summary_xml(citedbylist)

#for citation summary, code xcs/hcs (unless changed)
def print_citation_summary_xml(citedbylist):
    """Prints citation summary in xml."""
    alldict = calculate_citations(citedbylist)
    avgstr = str(alldict['avgcites'])
    totalcites = str(alldict['totalcites'])
    #format avg so that it does not span 10 digits
    avgstr = avgstr[0:4]
    reciddict = alldict['reciddict']
    #output formatting
    outp = "<citationsummary records=\""+str(len(citedbylist))
    outp += "\" citations=\""+str(totalcites)+"\">"
    for low, high, name in CFG_CITESUMMARY_FAME_THRESHOLDS:
        #get the name, print the value
        if reciddict.has_key(name):
            recs = reciddict[name]
            outp += "<citationclass>"+name
            outp += "<records>"+str(recs)+"</records>"
            outp += "</citationclass>\n"
    outp = outp + "</citationsummary>"
    #req.write(outp)
    return outp #just to return something

def calculate_citations(citedbylist):
    """calculates records in classes of citations
       defined by thresholds. returns a dictionary that
       contains total, avg, records and a dictionary
       of threshold names and number corresponding to it"""
    totalcites = 0
    avgcites = 0
    reciddict = {}
    for recid, cites in citedbylist:
        numcites = 0
        if cites:
            numcites = len(cites)
        totalcites = totalcites + numcites
        #take the numbers in CFG_CITESUMMARY_FAME_THRESHOLDS
        for low, high, name in CFG_CITESUMMARY_FAME_THRESHOLDS:
            if (numcites >= low) and (numcites <= high):
                if reciddict.has_key(name):
                    tmp = reciddict[name]
                    tmp.append(recid)
                    reciddict[name] = tmp
                else:
                    reciddict[name] = [recid]
    if (len(citedbylist) == 0):
        avgcites = 0
    else:
        avgcites = totalcites*1.0/len(citedbylist)

    #create a dictionary that contains all the values
    alldict = {}
    alldict['records'] = len(citedbylist)
    alldict['totalcites'] = totalcites
    alldict['avgcites'] = avgcites
    alldict['reciddict'] = reciddict
    return alldict


