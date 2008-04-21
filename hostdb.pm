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

1;