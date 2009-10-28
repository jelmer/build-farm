#!/usr/bin/perl

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

package hostdb;

use DBI;
use warnings;
use strict;

sub new($)
 {
    my ($class, $filename) = @_;
    
    my $dbh = DBI->connect("dbi:SQLite:$filename", "", "", {RaiseError => 1, PrintError => 0,
			 ShowErrorStatement => 1, AutoCommit => 0}) or return undef;
    
    my $self = { filename => $filename, dbh => $dbh };
    
    bless($self, $class);
}

sub provision($)
{
	my ($self) = @_;
	eval {
	    $self->{dbh}->do("CREATE TABLE host ( name text, owner text, owner_email text, password text, ssh_access int, fqdn text, platform text, permission text, last_dead_mail int, join_time int );");
	    
	    $self->{dbh}->do("CREATE UNIQUE INDEX unique_hostname ON host (name);");
	    
	    $self->{dbh}->do("CREATE TABLE build ( id integer primary key autoincrement, tree text, revision text, host text, compiler text, checksum text, age int, status text, commit_revision text);");
	    $self->{dbh}->do("CREATE UNIQUE INDEX unique_checksum ON build (checksum);");
	    
	    $self->{dbh}->do("CREATE TABLE test_run ( build int, test text, result text, output text);");
	    $self->{dbh}->commit();
	};
	if ($@) {
	    local $self->{dbh}->{RaiseError} = 0;
	    $self->{dbh}->rollback();
	    print "DB Failure: $@";
	    return 0;
	}
	return 1;
}

sub createhost($$$$$$)
{
	my ($self, $name, $platform, $owner, $owner_email, $password, $permission) = @_;
	my $sth = $self->{dbh}->prepare("INSERT INTO host (name, platform, owner, owner_email, password, permission, join_time) VALUES (?,?,?,?,?,?,?)");
	
	eval {
	    $sth->execute($name, $platform, $owner, $owner_email, $password, $permission, time());
	    $self->{dbh}->commit();
	};
	if ($@) {
	    local $self->{dbh}->{RaiseError} = 0;
	    $self->{dbh}->rollback();
	    print "DB Failure: $@";
	    return 0;
	}
	return 1;
}

sub deletehost($$)
{
	my ($self, $name) = @_;
	my $ret;
	my $sth = $self->{dbh}->prepare("DELETE FROM host WHERE name = ?");
	
	eval {
	    $ret = $sth->execute($name);
	    $self->{dbh}->commit();
	};
	if ($@) {
	    local $self->{dbh}->{RaiseError} = 0;
	    $self->{dbh}->rollback();
	    print "DB Failure: $@";
	    return 0;
	}
	
	return ($ret == 1);
}

sub hosts($)
{
	my ($self) = @_;
	
	return $self->{dbh}->selectall_arrayref("SELECT * FROM host ORDER BY name", { Slice => {} });
}

sub dead_hosts($$)
{
        my ($self, $age) = @_;
	my $dead_age = time() - $age;
	return $self->{dbh}->selectall_arrayref("SELECT host.name AS host, host.owner AS owner, host.owner_email AS owner_email, MAX(age) AS last_update FROM host LEFT JOIN build ON ( host.name == build.host) WHERE ifnull(last_dead_mail, 0) < $dead_age AND ifnull(join_time, 0) < $dead_age GROUP BY host.name having ifnull(MAX(age),0) < $dead_age", { Slice => {} });
}

sub sent_dead_mail($$) 
{
        my ($self, $host) = @_;
	my $changed;
	eval {
	    $changed = $self->{dbh}->do("UPDATE host SET last_dead_mail = ? WHERE name = ?", undef, 
		(time(), $host));
	    $self->{dbh}->commit();
	};
	if ($@) {
	    local $self->{dbh}->{RaiseError} = 0;
	    $self->{dbh}->rollback();
	    print "DB Failure: $@";
	    return 0;
	}
	
	return ($changed == 1);
}

sub host($$)
{
	my ($self, $name) = @_;
	
	my $hosts = $self->hosts();
	
	foreach (@$hosts) {
		return $_ if ($_->{name} eq $name);
	}
	
	return undef;
}

sub update_platform($$$)
{
	my ($self, $name, $new_platform) = @_;
	my $changed;

	eval {
	    $changed = $self->{dbh}->do("UPDATE host SET platform = ? WHERE name = ?", undef, 
		($new_platform, $name));
	    $self->{dbh}->commit();
	};
	if ($@) {
	    local $self->{dbh}->{RaiseError} = 0;
	    $self->{dbh}->rollback();
	    print "DB Failure: $@";
	    return 0;
	}
	
	return ($changed == 1);
}

sub update_owner($$$$)
{
	my ($self, $name, $new_owner, $new_owner_email) = @_;
	my $changed;

	eval {
	    $changed = $self->{dbh}->do("UPDATE host SET owner = ?, owner_email = ? WHERE name = ?", 
				       undef, ($new_owner, $new_owner_email, $name));
	    $self->{dbh}->commit();
	};
	if ($@) {
	    local $self->{dbh}->{RaiseError} = 0;
	    $self->{dbh}->rollback();
	    return 0;
	}
	
	return ($changed == 1);
}

# Write out the rsyncd.secrets
sub create_rsync_secrets($)
{
	my ($db) = @_;
	
	my $hosts = $db->hosts();
	
	my $res = "";
	
	$res .= "# rsyncd.secrets file\n";
	$res .= "# automatically generated by textfiles.pl. DO NOT EDIT!\n\n";
	
	foreach (@$hosts) {
		$res .= "# $_->{name}";
		if ($_->{owner}) {
			$res .= ", owner: $_->{owner} <$_->{owner_email}>\n";
		} else {
			$res .= ", owner unknown\n";
		}
		if ($_->{password}) {
			$res .= "$_->{name}:$_->{password}\n\n";
		} else {
			$res .= "# $->{name} password is unknown\n\n";
		}
	}
	
	return $res;
}

# Write out the web/
sub create_hosts_list($)
{
	my ($self) = @_;
	
	my $res = ""; 
	
	my $hosts = $self->hosts();
	
	foreach (@$hosts) {
		$res .= "$_->{name}: $_->{platform}\n";
	}
	
	return $res;
}

1;
