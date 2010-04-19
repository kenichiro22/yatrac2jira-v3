#!/usr/bin/python
# vim: set fileencoding=utf-8 :
"""
* Copyright (c) 2007 by Paweﾅ・Niewiadomski (Atlassian Pty Ltd)
* Copyright (c) 2009 by Tobias Richter (Diamond Light Source Ltd)
* Copyright (c) 2010 by Kenichiro Tanaka
* All rights reserved.
*
* Redistribution and use in source and binary forms, with or without
* modification, are permitted provided that the following conditions are met:
*     * Redistributions of source code must retain the above copyright
*       notice, this list of conditions and the following disclaimer.
*     * Redistributions in binary form must reproduce the above copyright
*       notice, this list of conditions and the following disclaimer in the
*       documentation and/or other materials provided with the distribution.
*     * Neither the name of the names of the contributors nor their 
*       organisations may be used to endorse or promote products derived 
*	from this software without specific prior written permission.
*
* THIS SOFTWARE IS PROVIDED BY THE COPY RIGHT HOLDERS ''AS IS'' AND ANY
* EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
* WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
* DISCLAIMED. IN NO EVENT SHALL THE COPY RIGHT HOLDERS BE LIABLE FOR ANY
* DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
* (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
* LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
* ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
* (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
* SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""
import sys
import codecs
import re
import time
import commands
import urllib
import os
import shutil
from trac.env import open_environment
from trac.ticket.model import *
from trac.ticket.query import Query
from trac.web.href import Href

usermap = {
    'randomguy' : 'newname',
    'admin' : 'ktana',
    'anonymous' : 'ktana',
    'nyma': 'nyama'
}

# Convert #111 -> TST-111 ?
ticketLinkConvert = True

# Decode attachment filename ?
decodeAttachmentFilename = True

# Temporary attachment path
tempAttachmentPath = 'temp'

components=[]
milestones=[]


class DummyHref:
	def ticket(self, id):
		return id

class DummyRef:
	def __init__(self):
		self.href=DummyHref()

def convertTicketLink(str, projkey):
    if ticketLinkConvert == False:
        return str
        
    if str == "":
        return str
    return re.sub(r'(?<!\!)#(\d+)', projkey + r'-\1', str)

def mapUser(user, default=""):
# here you have to specify your own code to map between Trac user and Jira user (maybe it can be transfered intact or using LDAP, AD, etc.)
# ....
    if user == "": 
       return default
    if (user == None): 
       return default
    # simple pattern match for email like "aaa <bbb@example.com>"
    m = re.match('.+<(.+)@.+>', user)
    if m != None:
       user = m.group(1)
    if user.find("@") > 0:
        user = user[0:user.find("@")]
    if usermap.has_key(user):
        user = usermap[user]    
    return user

def mapComponent(component):
    # de-uglify Trac-internal default value
    if component == "component1":
	return "unspecified"
    return component

def escape(str):
    str = str.replace("&", "&amp;").replace('"', '&quot;').replace("<", "&lt;").replace(">", "&gt;").replace("$", "&#36;").replace("*", "&#x2a;")
    str = str.replace("{","[").replace("}", "]").replace("[[[", "{noformat}").replace("]]]", "{noformat}").replace("+", "&#x2b;").replace("", " ").replace("", "\n").replace("", " ")
    return str.encode('iso8859-1', 'xmlcharrefreplace')

def mapIssueType(type):
    type = type.capitalize();
    if type == "Enhancement":
        return "Improvement"
    elif type == "Defect":
        return "Bug"
    elif type == "Task":
        return "Task"
    elif type == "Highlevel":
        return "Improvement"

    elif type == u'仕様変更':
        return 'Improvement'
    elif type == u'不具合':
        return "Bug"
    elif type == u'作業' or type == u'連絡' or type == u'課題':
        return "Task"
    elif type == u'機能追加':
        return "New Feature"

    sys.stderr.write("Fallback to Bug for "+type+"\n")
    return "Bug"

def mapPriority(p):
    #if p == "major" or p == "minor" or p == "normal" or p == "trivial" or p == "critical":
    #return p.capitalize();
    p = p.capitalize();

    if p == "Highest":
        return "Blocker"
    if p == "Blocker":
        return "Blocker"
    if p == "High":
        return "Critical"
    if p == "Critical":
        return "Critical"
    if p == "Medium":
        return "Major"
    if p == "Normal":
        return "Major"
    if p == "Major":
        return "Major"
    if p == "Minor":
        return "Minor"
    if p == "Low":
        return "Minor"
    if p == "Trivial":
        return "Trivial"
    if p == "Lowest":
        return "Trivial"

    if p == u"重大":
        return "Blocker"
    if p == "緊急":
        return "Critical"
    if p == "高":
        return "Major"
    if p == "中":
        return "Minor"
    if p == "低":
        return "Trivial"
    if p == "保留":
        return "Trivial"
    sys.stderr.write("Fallback to major priority for "+p+"\n")
    return "Major"

def mapResolution(r):
    if r == "wontfix":
        return "Won't Fix"
    elif r == "duplicate":
        return "Duplicate"
    elif r == "invalid":
        return "Incomplete"
    elif r == "worksforme":
        return "Cannot Reproduce"
    return "Fixed"
   
summaries = {}

def processTicket(env,id,owner):
    global summaries
    ticket = Ticket(env, id)
    # safeguard against deleted Milestones/Components that still exist in old Tickets
    # these are safe to use even if they exist
    createMilestone(ticket["milestone"])
    createComponent(ticket["component"],"",owner)
    print '<jira:CreateIssue issueKeyVar="key" issueType="'+mapIssueType(ticket["type"])+'"'
    # Determine unique summary. CreateIssue performs a case-insensitive
    # check unless duplicateSummary="ignore" is set
    sum = escape(ticket["summary"])
    sumkey = sum.upper()
    if summaries.has_key(sumkey):
        summaries[sumkey] += 1
        sum += " " + str(summaries[sumkey])
    else:
        summaries[sumkey] = 1
    print 'summary="'+ sum +'"'
    print 'priority="'+mapPriority(ticket["priority"])+'"'
    c = mapComponent(ticket["component"])
    if c != "":
        print 'components="'+c+'"'
    if ticket["milestone"] != "":
        print 'fixVersions="'+ticket["milestone"]+'"'
    if ticket["version"] != "":
        print 'versions="'+ticket["version"]+'"'

    v = mapUser(ticket["owner"], mapUser(ticket["reporter"], owner))
    if v != "":
        print 'assignee="'+ v +'"'

    v = mapUser(ticket["reporter"], owner)
    print 'reporter="'+ v +'"'

    if ticket["keywords"] != "":
        print 'environment="'+ticket["keywords"]+'"'
    print 'description="'+escape(convertTicketLink(ticket["description"], env.projkey))+'"'
    print 'updated="'+time.strftime("%Y-%m-%d %H:%M:%S.0", time.gmtime(ticket.time_changed))+'"'
    print 'created="'+time.strftime("%Y-%m-%d %H:%M:%S.0", time.gmtime(ticket.time_created))+'"'
    print '/>'

    state = "open"
    if ticket["status"] == "closed":
        state = "closed"
        print '<jira:TransitionWorkflow key="${key}" user="'+mapUser(ticket["owner"], owner)+'" workflowAction="Close Issue"'
        print ' resolution="'+mapResolution(ticket["resolution"])+'"/>'

    for ch in ticket.get_changelog():
        if ch[2] == "comment" and ch[4] != "":
            print '<jira:AddComment issue-key="${key}" created="'+time.strftime("%Y-%m-%d %H:%M:%S.0", time.gmtime(ch[0]))+'" '
            print ' commenter="'+mapUser(ch[1])+'"'
            print ' comment="'+escape(convertTicketLink(ch[4], env.projkey))+'"/>'
        elif ch[2] == "resolution":
            if state == "closed":
                print '<jira:TransitionWorkflow key="${key}" user="'+mapUser(ch[1])+'" workflowAction="Reopen Issue"/>'
            print '<jira:TransitionWorkflow key="${key}" user="'+mapUser(ch[1])+'" workflowAction="Close Issue"'
            print ' resolution="'+mapResolution(ch[4])+'"/>'
            state = "closed"
        elif ch[2] == "attachment":
            attachfile = env.path + "/attachments/ticket/" + str(ticket.id) + "/" + urllib.quote(ch[4].encode())
            if os.path.isfile(attachfile) :
                if decodeAttachmentFilename : 
                    attachdir = tempAttachmentPath + "/attachments/ticket/" + str(ticket.id) + "/"
                    if not os.path.isdir(attachdir):
                        os.makedirs(attachdir)
                    filename = attachdir + ch[4]
                    shutil.copy(attachfile, filename)
                else:
                    filename = env.path + "/attachments/ticket/" + str(ticket.id) + "/" + urllib.quote(ch[4].encode)
                print '<jira:AttachFile key="${key}" filepath="' + filename + '" option="override"/>'
            else:
                sys.stderr.write(ch[4] + ' does not exist.\n')

def createComponent(name, desc, user):
	name = mapComponent(name)
	if name in components:
		return
	if name != "":
		print '<jira:AddComponent name="'+ name +'" description="' + desc + '" componentLead="'+ mapUser(user) +'"/>'
		components.append(name)

def createMilestone(name):
	if name in milestones:
		return
	if name != "":
		print '<jira:AddVersion name="' + name + '"/>'
		milestones.append(name)

def main():
    sys.stderr = codecs.getwriter('shift_jis')(sys.stderr)

    sys.stderr.write("Running "+sys.argv[0]+"..\n")
    env = open_environment(sys.argv[1])
    env.projkey=sys.argv[2]
    owner = sys.argv[3]
    ref = DummyRef()

    print '<?xml version="1.0"?>'
    print '<JiraJelly xmlns:jira="jelly:com.atlassian.jira.jelly.enterprise.JiraTagLib">'
    print '<jira:CreateProject key="'+env.projkey+'" name="' + env.config.get('project', 'descr') + '" lead="'+owner+'">'
    print '''
<jira:CreatePermissionScheme name="'''+env.projkey+'''-scheme">
<jira:AddPermission permissions="Assignable,Browse,Create,Assign,Resolve,Close,ModifyReporter,Attach,Comment"
group="jira-users"
type="group"/>
<jira:SelectProjectScheme/>
</jira:CreatePermissionScheme> 
	'''
    for c in Component(env).select(env):
    	createComponent(c.name,c.description,c.owner)
    for v in Version(env).select(env):
        createMilestone(v.name)
    tickets=[]
    for t in Query(env).execute(ref):
	tickets.append(int(t["id"]))
    tickets.sort()
    i = 0
    for t in tickets:

        processTicket(env, t, owner)
    print '</jira:CreateProject>'
    print '</JiraJelly>'

if __name__ == "__main__":
	main()
