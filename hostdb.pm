#!/usr/bin/perl

package hostdb;

use DBI;

sub new($)
 {
    my ($class, $filename) = @_;
    
    my $dbh = DBI->connect("dbi:SQLite:$filename") or die("Unable to open SQLite database $filename: $!");
    
    my $self = { filename => $filename, dbh => $dbh };
    
    bless($self, $class);
}

sub provision($)
{
	my ($self) = @_;
	
	$self->{dbh}->do("CREATE TABLE host ( name text, owner text, owner_email text, ssh_access int, platform text, permission text );");
}

sub createhost($$$$$$)
{
	my ($self, $name, $platform, $owner, $owner_email, $permission) = @_;
	my $sth = $self->{dbh}->prepare("INSERT INTO host (name, platform, owner, owner_email, permission) VALUES (?,?,?,?,?)");
	
	$sth->execute($name, $platform, $owner, $owner_email, $permission);
}

sub deletehost($$)
{
	my ($self, $name) = @_;
	
	my $sth = $self->{dbh}->prepare("DELETE FROM host WHERE name = ?");
	
	$sth->execute($name);
}

1;