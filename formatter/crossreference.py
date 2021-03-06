"""
Searches for citations to Bailii files
"""

import re
import os
from general import *
import prefixtree


# trying citationtree as a global variable
citationtree = prefixtree.PrefixTree()


def crossreference(file_list, dbfile_name, logfile, use_multiprocessing):

    print "-"*25
    print "Crossreferencing..."

    # counts files processed
    finished_count = Counter()

    with DatabaseManager(dbfile_name,use_multiprocessing) as cursor:
        create_table(cursor)

        print "Making prefix tree"
        cursor.execute('SELECT DISTINCT citationcode,citationcodeid FROM citationcodes ORDER BY citationcode')
        sorted_citations = [(a,i) for (a,i) in cursor]
        citationtree.populate(sorted_citations)
        broadcast(logfile,"Read %d citation codes from database"%len(sorted_citations))

        def crossreference_report(basename):
            "Callback function; reports on success or failure"
            def closure(r):
                "Take True and a set of citations, or false and a message"
                (s,m) = r
                try:
                    if s:
                        write_crossreferences_to_sql(m,basename,cursor)
                        finished_count.inc()
                        print "crossreference:%6d. %s"%(finished_count.count,basename)
                    else:
                        raise StandardConversionError(m)
                except ConversionError,e:
                    e.log("crossreference",basename,logfile)
            return closure

        print "Searching through files"
        with ProcessManager(use_multiprocessing) as process_pool:
            for fullname in file_list:
                basename = os.path.basename(fullname)
                process_pool.apply_async(crossreference_file,(fullname,basename,dbfile_name,use_multiprocessing),callback=crossreference_report(basename))

        # remove duplicates
        broadcast(logfile,"Successfully searched %d files for crossreferences"%finished_count.count)
        cursor.execute('SELECT count() FROM crossreferences')
        crossreference_count = cursor.fetchone()[0]
        broadcast(logfile,"Found %d crossreferences (including selfreferences)"%crossreference_count)
        cursor.execute('DELETE FROM crossreferences WHERE crossreferenceid IN (SELECT crossreferenceid FROM crossreferences JOIN judgmentcodes ON crossreferences.citationcodeid = judgmentcodes.citationcodeid WHERE crossreferences.judgmentid = judgmentcodes.judgmentid)')
        cursor.execute('SELECT count() FROM crossreferences')
        crossreference_count = cursor.fetchone()[0]
        broadcast(logfile,"Found %d crossreferences (after removing selfreferences)"%crossreference_count)



def create_table(cursor):
    create_tables_interactively(cursor,['crossreferences'],['CREATE TABLE crossreferences (crossreferenceid INTEGER PRIMARY KEY ASC, judgmentid INTEGER, citationcodeid INTEGER)', 'CREATE INDEX crossreferences_judgmentid ON crossreferences (judgmentid)', 'CREATE INDEX crossreferences_citationcodeid ON crossreferences (citationcodeid)'])


def crossreference_file(fullname,basename,dbfile_name,use_multiprocessing):
    # returns a set of other cited judgments
    try:
        f = open_bailii_html(fullname)
        citationset = set()
        for (_,v) in citationtree.search(reduce(prefixtree.compose_normalisers,[prefixtree.remove_excess_spaces,prefixtree.remove_html,prefixtree.character_removing_normaliser(".'")]),f.read()):
            citationset.add(v)
        return (True,citationset)
    except ConversionError, e:
        return (False,e.message)



def write_crossreferences_to_sql(citationset,basename,cursor):
    try:
        jids = list(cursor.execute('SELECT judgmentid FROM judgments WHERE filename=?',(basename,)))
        if len(jids)>0:
            judgmentid = jids[0][0]
        else:
            raise NoMetadata
        for citationcodeid in citationset:
            cursor.execute('INSERT INTO crossreferences(judgmentid,citationcodeid) VALUES (?,?)', (judgmentid,citationcodeid))
    except sqlite.IntegrityError, e:
        raise SqliteIntegrityError(e)


