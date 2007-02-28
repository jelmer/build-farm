use ExtUtils::MakeMaker;

WriteMakefile(
    'NAME'	=> 'BuildFarm',
    'VERSION_FROM' => 'build.pm',
	'EXE_FILES' => [ 'fill_db.pl', 'web/build.pl' ],
	'test' => { 'TESTS' => 'tests/*.pl' }
);
