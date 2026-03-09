-- Historical NBA player records for ML training reference dimension table.
-- Representative roster covering teams active in the 2022-23 and 2023-24 seasons.
-- Idempotent: ON CONFLICT (id) DO NOTHING means safe to run multiple times.
--
-- NOTE: These player records provide FK targets for tracking_coordinates rows.
-- Actual tracking_coordinates data (frame-by-frame positions) must be populated
-- by running the video pipeline on real game footage (plan 01-04).

INSERT INTO players (id, name, team, jersey_number, position) VALUES
-- Los Angeles Lakers (LAL)
('b1000001-0000-4000-8000-000000000001', 'LeBron James',       'LAL',  6,  'SF'),
('b1000001-0000-4000-8000-000000000002', 'Anthony Davis',      'LAL',  3,  'PF'),
('b1000001-0000-4000-8000-000000000003', 'Austin Reaves',      'LAL', 15,  'SG'),
-- Golden State Warriors (GSW)
('b1000001-0000-4000-8000-000000000004', 'Stephen Curry',      'GSW', 30,  'PG'),
('b1000001-0000-4000-8000-000000000005', 'Klay Thompson',      'GSW', 11,  'SG'),
('b1000001-0000-4000-8000-000000000006', 'Draymond Green',     'GSW', 23,  'PF'),
-- Boston Celtics (BOS)
('b1000001-0000-4000-8000-000000000007', 'Jayson Tatum',       'BOS',  0,  'SF'),
('b1000001-0000-4000-8000-000000000008', 'Jaylen Brown',       'BOS',  7,  'SG'),
('b1000001-0000-4000-8000-000000000009', 'Jrue Holiday',       'BOS', 12,  'PG'),
-- Milwaukee Bucks (MIL)
('b1000001-0000-4000-8000-000000000010', 'Giannis Antetokounmpo', 'MIL', 34, 'PF'),
('b1000001-0000-4000-8000-000000000011', 'Damian Lillard',     'MIL',  0,  'PG'),
('b1000001-0000-4000-8000-000000000012', 'Khris Middleton',    'MIL', 22,  'SF'),
-- Phoenix Suns (PHX)
('b1000001-0000-4000-8000-000000000013', 'Kevin Durant',       'PHX', 35,  'SF'),
('b1000001-0000-4000-8000-000000000014', 'Devin Booker',       'PHX',  1,  'SG'),
('b1000001-0000-4000-8000-000000000015', 'Bradley Beal',       'PHX',  3,  'PG'),
-- Denver Nuggets (DEN)
('b1000001-0000-4000-8000-000000000016', 'Nikola Jokic',       'DEN', 15,  'C'),
('b1000001-0000-4000-8000-000000000017', 'Jamal Murray',       'DEN', 27,  'PG'),
('b1000001-0000-4000-8000-000000000018', 'Michael Porter Jr.', 'DEN', 13,  'SF'),
-- Miami Heat (MIA)
('b1000001-0000-4000-8000-000000000019', 'Jimmy Butler',       'MIA', 22,  'SF'),
('b1000001-0000-4000-8000-000000000020', 'Bam Adebayo',        'MIA', 13,  'C'),
-- Philadelphia 76ers (PHI)
('b1000001-0000-4000-8000-000000000021', 'Joel Embiid',        'PHI', 21,  'C'),
('b1000001-0000-4000-8000-000000000022', 'Tyrese Maxey',       'PHI',  0,  'PG'),
-- New York Knicks (NYK)
('b1000001-0000-4000-8000-000000000023', 'Jalen Brunson',      'NYK', 11,  'PG'),
('b1000001-0000-4000-8000-000000000024', 'Julius Randle',      'NYK', 30,  'PF'),
-- Cleveland Cavaliers (CLE)
('b1000001-0000-4000-8000-000000000025', 'Donovan Mitchell',   'CLE', 45,  'SG'),
('b1000001-0000-4000-8000-000000000026', 'Evan Mobley',        'CLE',  4,  'C'),
-- Sacramento Kings (SAC)
('b1000001-0000-4000-8000-000000000027', 'De''Aaron Fox',      'SAC',  5,  'PG'),
('b1000001-0000-4000-8000-000000000028', 'Domantas Sabonis',   'SAC', 11,  'C'),
-- Minnesota Timberwolves (MIN)
('b1000001-0000-4000-8000-000000000029', 'Anthony Edwards',    'MIN',  5,  'SG'),
('b1000001-0000-4000-8000-000000000030', 'Karl-Anthony Towns', 'MIN', 32,  'C'),
-- Oklahoma City Thunder (OKC)
('b1000001-0000-4000-8000-000000000031', 'Shai Gilgeous-Alexander', 'OKC', 2, 'PG'),
('b1000001-0000-4000-8000-000000000032', 'Josh Giddey',        'OKC',  3,  'SF'),
-- Memphis Grizzlies (MEM)
('b1000001-0000-4000-8000-000000000033', 'Ja Morant',          'MEM', 12,  'PG'),
('b1000001-0000-4000-8000-000000000034', 'Jaren Jackson Jr.',  'MEM', 13,  'PF'),
-- Dallas Mavericks (DAL)
('b1000001-0000-4000-8000-000000000035', 'Luka Doncic',        'DAL', 77,  'PG'),
('b1000001-0000-4000-8000-000000000036', 'Kyrie Irving',       'DAL', 11,  'PG'),
-- New Orleans Pelicans (NOP)
('b1000001-0000-4000-8000-000000000037', 'Zion Williamson',    'NOP',  1,  'PF'),
('b1000001-0000-4000-8000-000000000038', 'Brandon Ingram',     'NOP', 14,  'SF')
ON CONFLICT (id) DO NOTHING;
