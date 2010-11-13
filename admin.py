#!/usr/bin/python
# Samba.org buildfarm
# Copyright (C) 2008 Andrew Bartlett <abartlet@samba.org>
# Copyright (C) 2008 Jelmer Vernooij <jelmer@samba.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from buildfarm import (
    hostdb,
    BuildFarm,
    )
import commands
import os
import smtplib
import sys
import time
from email.MIMEText import MIMEText

buildfarm = BuildFarm()

db = buildfarm.hostdb

def update_rsyncd_secrets():
    temp_rsyncd_secrets = os.path.join(os.path.dirname(__file__), "../rsyncd.secrets.new")
    f = open(temp_rsyncd_secrets, "w")
    f.writelines(db.create_rsync_secrets())
    f.close()

    os.rename(temp_rsyncd_secrets, "../rsyncd.secrets")

def update_hosts_list():
    temp_hosts_list_file = os.path.join(os.path.dirname(__file__), "web", "hosts.list.new")
    f = open(temp_hosts_list_file, "w")
    f.writelines(db.create_hosts_list())
    f.close()

    os.rename(temp_hosts_list_file, os.path.join(os.path.dirname(__file__), "web/hosts.list"))

dry_run = False

print "Samba Build farm management tool"
print "================================"

if len(sys.argv) > 1:
    op = sys.argv[1]
else:
    print "Add Machine to build farm:      add"
    print "Remove Machine from build farm: remove"
    print "Modify build farm account:      modify"
    print "Print build farm host info:     info"
    print "Print build farm host list:     list"

    op = raw_input("Select Operation: [add] ").lower()

    if op == "":
        op = "add"

if op == "remove":
    hostname = raw_input("Please enter hostname to delete: ")
    try:
        db.deletehost(hostname.decode("utf-8"))
    except hostdb.NoSuchHost, e:
        print "No such host '%s'" % e.name
        sys.exit(1)
    else:
        db.commit()
        update_rsyncd_secrets()
        update_hosts_list()
elif op == "modify":
    hostname = raw_input("Please enter hostname to modify: ")
    try:
        host = db.host(hostname.decode("utf-8"))
    except hostdb.NoSuchHost, e:
        print "No such host '%s'" % e.name
        sys.exit(1)
    print "Owner: %s <%s>" % host.owner
    print "Platform: %s" % host.platform
    print ""
    mod_op = raw_input("Modify owner or platform: [platform] ")
    if mod_op == "":
        mod_op = "platform"
    if mod_op == "platform":
        platform = raw_input("Enter new platform: ")
        host.update_platform(platform.decode("utf-8"))
        db.commit()
    elif mod_op == "owner":
        owner = raw_input("Enter new owner's name: ")
        owner_email = raw_input("Enter new owner's e-mail address: ")
        host.update_owner(owner.decode("utf-8"), owner_email.decode("utf-8"))
        db.commit()
    else:
        print "Unknown subcommand %s" % mod_op
        sys.exit(1)
    update_rsyncd_secrets()
    update_hosts_list()
elif op == "add":
    hostname = raw_input("Machine hostname: ")
    try:
        db.host(hostname.decode("utf-8"))
    except hostdb.NoSuchHost, e:
        pass
    else:
        print "A host with the name %s already exists." % e.name
        sys.exit(1)
    platform = raw_input("Machine platform (eg Fedora 9 x86_64): ")
    owner = raw_input("Machine Owner Name: ")
    owner_email = raw_input("Machine Owner E-mail: ")
    password = raw_input("Enter password: [generate random] ")
    if password == "":
        password = commands.getoutput("pwgen 16 1").strip()
        print "Password will be: %s" % password
    permission = []
    print "Enter permission e-mail, finish with a ."
    line = raw_input("")
    while line != ".":
        permission += line
        line = raw_input("")

    try:
        db.createhost(hostname.decode("utf-8"), platform.decode("utf-8"),
            owner.decode("utf-8"), owner_email.decode("utf-8"),
            password.decode("utf-8"),
            "".join(permission).decode("utf-8", "replace"))
    except hostdb.HostAlreadyExists, e:
        print "A host with the name %s already exists." % e.name
        sys.exit(1)
    else:
        db.commit()

    body = """
Welcome to the Samba.org build farm.  

Your host %(hostname)s has been added to the Samba Build farm.  

We have recorded that it is running %(platform)s.  

If you have not already done so, please read:
http://build.samba.org/instructions.html

The password for your rsync .password file is %(password)s

An e-mail asking you to subscribe to the build-farmers mailing
list will arrive shortly.  Please ensure you maintain your 
subscription to this list while you have hosts in the build farm.

Thank you for your contribution to ensuring portability and quality
of Samba.org projects.


""" % { "hostname": hostname, "platform": platform, "password": password }

    msg_notification = MIMEText(body)

    # send the password in an e-mail to that address
    msg_notification["Subject"] = "Your new build farm host %s" % hostname
    msg_notification["To"] = "\"%s\" <%s>" % (owner, owner_email)
    msg_notification["Bcc"] = "build@samba.org"
    msg_notification["From"] = "\"Samba Build Farm\" <build@samba.org>"

    msg_subscribe = MIMEText("""Please subscribe %s to the build-farmers mailing list

Thanks, your friendly Samba build farm administrator <build@samba.org>""" % owner)
    msg_subscribe["From"] = "\"%s\" <%s>" % (owner, owner_email)
    msg_subscribe["Subject"] = 'Subscribe to build-farmers mailing list'
    msg_subscribe["To"] = 'build-farmers-join@lists.samba.org'

    if dry_run:
        print msg_notification
    else:
        s = smtplib.SMTP()
        s.connect()
        for msg in (msg_notification, msg_subscribe):
            recipients = [msg["To"]]
            if msg["Bcc"]:
                recipients.append(msg["Bcc"])
            s.sendmail(msg["From"], recipients, msg.as_string())
        s.quit()
        update_rsyncd_secrets()
        update_hosts_list()
elif op == "info":
    hostname = raw_input("Hostname: ")
    try:
        host = db.host(hostname.decode("utf-8"))
    except hostdb.NoSuchHost, e:
        print "No such host '%s'" % e.name
        sys.exit(1)
    if host.fqdn:
        opt_fqdn = " (%s)" % host.fqdn
    else:
        opt_fqdn = ""
    print "Host: %s%s" % (host.name, opt_fqdn)
    print "Platform: %s" % host.platform
    print "Owner: %s <%s>" % host.owner
elif op == "list":
    for host in db.host_ages():
        if host.last_update:
            age = time.time() - host.last_update
        else:
            age = ""
        print "%-12s %s" % (age, host.name)
else:
    print "Unknown command %s" % op
    sys.exit(1)
