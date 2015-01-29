# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2009, 2010, 2011, 2012, 2013, 2014, 2015 CERN.
#
# Invenio is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# Invenio is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Invenio; if not, write to the Free Software Foundation, Inc.,
# 59 Temple Place, Suite 330, Boston, MA 02111-1307, USA.

"""
Provide a "ticket" interface with a request tracker.
This is a subclass of BibCatalogSystem
"""

import os
import re
import rt
import invenio.webuser
from invenio.shellutils import run_shell_command, escape_shell_arg
from invenio.bibcatalog_system import BibCatalogSystem, get_bibcat_from_prefs

from invenio.config import CFG_BIBCATALOG_SYSTEM, \
    CFG_BIBCATALOG_SYSTEM_RT_URL, \
    CFG_BIBCATALOG_SYSTEM_RT_DEFAULT_USER, \
    CFG_BIBCATALOG_SYSTEM_RT_DEFAULT_PWD, \
    CFG_BIBEDIT_ADD_TICKET_RT_QUEUES


class BibCatalogSystemRT(BibCatalogSystem):

    def _get_instance(self, uid=None):
        """
        Return a valid RT instance.
        """
        username, passwd = None, None
        if uid:
            username, passwd = get_bibcat_from_prefs(uid)
        if username is None or not uid:
            username = CFG_BIBCATALOG_SYSTEM_RT_DEFAULT_USER
            passwd = CFG_BIBCATALOG_SYSTEM_RT_DEFAULT_PWD
        if not username or not passwd:
            raise RuntimeError("No valid RT user login specified")
        tracker = rt.Rt(
            url=CFG_BIBCATALOG_SYSTEM_RT_URL + '/REST/1.0/',
            default_login=username,
            default_password=passwd,
        )
        tracker.login()
        return tracker

    def check_system(self, uid=None):
        """return an error string if there are problems"""
        if not CFG_BIBCATALOG_SYSTEM == 'RT':
            return "CFG_BIBCATALOG_SYSTEM is not RT though this is an RT module"

        if not CFG_BIBCATALOG_SYSTEM_RT_URL:
            return "CFG_BIBCATALOG_SYSTEM_RT_URL not defined or empty"
        # Construct URL, split RT_URL at //
        if not CFG_BIBCATALOG_SYSTEM_RT_URL.startswith('http://') and \
           not CFG_BIBCATALOG_SYSTEM_RT_URL.startswith('https://'):
            return "CFG_BIBCATALOG__SYSTEM_RT_URL does not start with 'http://' or 'https://'"

        try:
            self._get_instance(uid)
        except Exception as err:
            return "could not connect to %s: %s" % (CFG_BIBCATALOG_SYSTEM_RT_URL, err)
        return ""

    def ticket_search(self, uid, recordid=-1, subject="", text="", creator="",
                      owner="", date_from="", date_until="", status="",
                      priority="", queue=""):
        """returns a list of ticket ID's related to this record or by
           matching the subject, creator or owner of the ticket."""

        search_atoms = {}
        if recordid > -1:
            # search by recid
            search_atoms['CF.{RecordID}'] = str(recordid)
        if subject:
            # search by subject
            search_atoms['Subject__like'] = str(subject)
        if text:
            search_atoms['Content__like'] = str(text)
        if str(creator):
            # search for this person's bibcatalog_username in preferences
            creatorprefs = invenio.webuser.get_user_preferences(creator)
            creator = "Nobody can Have This Kind of Name"
            if "bibcatalog_username" in creatorprefs:
                creator = creatorprefs["bibcatalog_username"]
            search_atoms['Creator'] = str(creator)
        if str(owner):
            ownerprefs = invenio.webuser.get_user_preferences(owner)
            owner = "Nobody can Have This Kind of Name"
            if "bibcatalog_username" in ownerprefs:
                owner = ownerprefs["bibcatalog_username"]
            search_atoms['Owner'] = str(owner)
        if date_from:
            search_atoms['Created__gt'] = str(date_from)
        if date_until:
            search_atoms['Created__lt'] = str(date_until)
        if str(status) and isinstance(status, type("this is a string")):
            search_atoms['Status'] = str(status)
        if str(priority):
            # Try to convert to int
            intpri = -1
            try:
                intpri = int(priority)
            except ValueError:
                pass
            if intpri > -1:
                search_atoms['Priority'] = str(intpri)
        if queue:
            search_atoms['Queue'] = str(queue)
        tickets = []

        if not search_atoms:
            return tickets

        rt_instance = self._get_instance(uid)
        tickets = rt_instance.search(**search_atoms)
        return [int(ticket[u'id'].split('/')[1]) for ticket in tickets]

    def ticket_submit(self, uid=None, subject="", recordid=-1, text="",
                      queue="", priority="", owner="", requestor=""):
        atoms = {}
        if subject:
            atoms['Subject'] = str(subject)
        if recordid:
            atoms['CF.RecordID'] = str(recordid)
        if priority:
            atoms['Priority'] = str(priority)
        if queue:
            atoms['Queue'] = str(queue)
        if requestor:
            atoms['Requestor'] = str(requestor)
        if owner:
            # get the owner name from prefs
            ownerprefs = invenio.webuser.get_user_preferences(owner)
            if "bibcatalog_username" in ownerprefs:
                owner = ownerprefs["bibcatalog_username"]
                atoms['Owner'] = str(owner)
        if text:
            atoms['Text'] = str(text)

        rt_instance = self._get_instance(uid)
        return rt_instance.create_ticket(**atoms)

    def ticket_comment(self, uid, ticketid, comment):
        """comment on a given ticket. Returns 1 on success, 0 on failure"""

        rt_instance = self._get_instance(uid)
        return rt_instance.comment(ticketid, comment)

    def ticket_assign(self, uid, ticketid, to_user):
        """assign a ticket to an RT user. Returns 1 on success, 0 on failure"""

        rt_instance = self._get_instance(uid)
        return rt_instance.edit_ticket(ticketid, Owner=to_user)

    def ticket_set_attribute(self, uid, ticketid, attribute, new_value):
        """change the ticket's attribute. Returns 1 on success, 0 on failure"""
        # check that the attribute is accepted..
        if attribute not in BibCatalogSystem.TICKET_ATTRIBUTES:
            return 0
        # we cannot change read-only values.. including text that is an
        # attachment. pity
        if attribute in ['creator', 'date', 'ticketid', 'url_close', 'url_display', 'recordid', 'text']:
            return 0
        # check attribute
        atom = {}
        if attribute == 'priority':
            if not str(new_value).isdigit():
                return 0
            atom['Priority'] = str(new_value)

        if attribute == 'subject':
            atom['Subject'] = str(new_value)

        if attribute == 'owner':
            # convert from invenio to RT
            ownerprefs = invenio.webuser.get_user_preferences(new_value)
            if "bibcatalog_username" not in ownerprefs:
                return 0
            atom['Owner'] = str(ownerprefs['bibcatalog_username'])

        if attribute == 'status':
            atom['Status'] = str(new_value)

        if attribute == 'queue':
            atom['Queue'] = str(new_value)

        # make sure ticketid is numeric
        try:
            dummy = int(ticketid)
        except ValueError:
            return 0

        rt_instance = self._get_instance(uid)
        return rt_instance.edit_ticket(ticketid, **atom)

    def ticket_get_attribute(self, uid, ticketid, attribute):
        """return an attribute of a ticket"""
        ticinfo = self.ticket_get_info(uid, ticketid, [attribute])
        if attribute in ticinfo:
            return ticinfo[attribute]
        return None

    def ticket_get_info(self, uid, ticketid, attributes = None):
        """return ticket info as a dictionary of pre-defined attribute names.
           Or just those listed in attrlist.
           Returns None on failure"""
        # Make sure ticketid is not None
        if not ticketid:
            return 0
        if attributes is None:
            attributes = []

        rt_instance = self._get_instance(uid)
        tdict = {}
        for key, value in rt_instance.get_ticket(ticketid).items():
            if isinstance(value, list):
                value = [elem.encode('utf8') for elem in value]
            else:
                value = value.encode('utf8')
            key = key.lower().encode('utf8')
            if key == 'cf.{recordid}':
                key = 'recordid'
            if key == 'id':
                tdict[key] = int(value.split('/')[1])
            tdict[key] = value

        attachments = rt_instance.get_attachments_ids(ticketid)

        text = [rt_instance.get_attachment_content(
            ticketid, attachment) for attachment in attachments]
        tdict['text'] = '\n'.join(text)

        tdict['url_display'] = CFG_BIBCATALOG_SYSTEM_RT_URL + \
            "/Ticket/Display.html?id=" + str(ticketid)
        tdict['url_close'] = CFG_BIBCATALOG_SYSTEM_RT_URL + \
            "/Ticket/Update.html?Action=Comment&DefaultStatus=resolved&id=" + \
            str(ticketid)
        tdict['url_modify'] = CFG_BIBCATALOG_SYSTEM_RT_URL + \
            "/Ticket/ModifyAll.html?id=" + str(ticketid)

        tdict['owner'] = invenio.webuser.get_uid_based_on_pref(
            "bibcatalog_username", tdict['owner'])
        return tdict

    def get_queues(self, uid):
        """get all the queues from RT. Returns a list of queues"""
        # get all queues with id from 1-100 in order to get all the available queues.
        # Then filters the queues keeping these selected in the configuration
        # variable
        queues = []

        rt_instance = self._get_instance(uid)
        for i in range(1, 100):
            queue = rt_instance.get_queue(i)
            if queue and queue[u'Disabled'] == u'0':
                queues.append(queue[u'Name'])
        return queues
