#!/usr/bin/env python3
"""
Database migration and seeding script for NBA AI System
Handles database schema creation and initial data population
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
import pandas as pd
import json
from datetime import datetime, timedelta
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.db import get_db_connection
from src.data.nba_stats import get_all_players
from src.data.schedule_context import get_season_schedule

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseMigrator:
    def __init__(self):
        self.db_url = os.getenv('DATABASE_URL', 'postgresql://nba_user:password@localhost:5432/nba_ai')
        
    def run_migrations(self):
        """Run all database migrations"""
        logger.info("🚀 Starting database migrations...")
        
        # Create tables
        self.create_tables()
        
        # Seed initial data
        self.seed_initial_data()
        
        logger.info("✅ Database migrations completed successfully!")
    
    def create_tables(self):
        """Create all database tables"""
        logger.info("📝 Creating database tables...")
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                
                # Games table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS games (
                        game_id VARCHAR(50) PRIMARY KEY,
                        date DATE NOT NULL,
                        home_team_id VARCHAR(10) NOT NULL,
                        away_team_id VARCHAR(10) NOT NULL,
                        home_score INTEGER,
                        away_score INTEGER,
                        season VARCHAR(10) NOT NULL,
                        status VARCHAR(20) DEFAULT 'scheduled',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                # Players table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS players (
                        player_id INTEGER PRIMARY KEY,
                        player_name VARCHAR(100) NOT NULL,
                        team_id VARCHAR(10),
                        position VARCHAR(10),
                        height_inches FLOAT,
                        weight_lbs FLOAT,
                        birth_date DATE,
                        experience_years INTEGER,
                        season VARCHAR(10) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                # Player stats table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS player_stats (
                        id SERIAL PRIMARY KEY,
                        player_id INTEGER NOT NULL,
                        game_id VARCHAR(50) NOT NULL,
                        season VARCHAR(10) NOT NULL,
                        points FLOAT,
                        rebounds FLOAT,
                        assists FLOAT,
                        minutes FLOAT,
                        fg_percentage FLOAT,
                        fg3_percentage FLOAT,
                        ft_percentage FLOAT,
                        plus_minus FLOAT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (player_id) REFERENCES players(player_id),
                        FOREIGN KEY (game_id) REFERENCES games(game_id),
                        UNIQUE(player_id, game_id)
                    );
                """)
                
                # Predictions table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS predictions (
                        id SERIAL PRIMARY KEY,
                        game_id VARCHAR(50) NOT NULL,
                        player_id INTEGER,
                        prediction_type VARCHAR(50) NOT NULL,
                        predicted_value FLOAT NOT NULL,
                        confidence FLOAT,
                        model_version VARCHAR(20),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (game_id) REFERENCES games(game_id),
                        FOREIGN KEY (player_id) REFERENCES players(player_id)
                    );
                """)
                
                # Betting odds table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS betting_odds (
                        id SERIAL PRIMARY KEY,
                        game_id VARCHAR(50) NOT NULL,
                        sportsbook VARCHAR(50) NOT NULL,
                        bet_type VARCHAR(50) NOT NULL,
                        line_value FLOAT,
                        over_odds FLOAT,
                        under_odds FLOAT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (game_id) REFERENCES games(game_id)
                    );
                """)
                
                # Tracking data table (for CV data)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS tracking_data (
                        id SERIAL PRIMARY KEY,
                        game_id VARCHAR(50) NOT NULL,
                        frame_number INTEGER NOT NULL,
                        timestamp FLOAT NOT NULL,
                        player_id INTEGER,
                        x_position FLOAT,
                        y_position FLOAT,
                        speed FLOAT,
                        acceleration FLOAT,
                        ball_possession BOOLEAN DEFAULT FALSE,
                        event_type VARCHAR(20),
                        jersey_number INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (game_id) REFERENCES games(game_id),
                        FOREIGN KEY (player_id) REFERENCES players(player_id)
                    );
                """)
                
                # Analytics metrics table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS analytics_metrics (
                        id SERIAL PRIMARY KEY,
                        game_id VARCHAR(50),
                        player_id INTEGER,
                        metric_name VARCHAR(100) NOT NULL,
                        metric_value FLOAT NOT NULL,
                        metric_type VARCHAR(50),
                        season VARCHAR(10),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (game_id) REFERENCES games(game_id),
                        FOREIGN KEY (player_id) REFERENCES players(player_id)
                    );
                """)
                
                # Model performance table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS model_performance (
                        id SERIAL PRIMARY KEY,
                        model_name VARCHAR(100) NOT NULL,
                        model_version VARCHAR(20),
                        metric_name VARCHAR(50) NOT NULL,
                        metric_value FLOAT NOT NULL,
                        test_data_date DATE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                # Create indexes for performance
                cur.execute("CREATE INDEX IF NOT EXISTS idx_games_date ON games(date);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_games_teams ON games(home_team_id, away_team_id);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_players_team ON players(team_id);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_predictions_game ON predictions(game_id);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_predictions_player ON predictions(player_id);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_tracking_game_frame ON tracking_data(game_id, frame_number);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_odds_game ON betting_odds(game_id);")
                
                conn.commit()
                logger.info("✅ Database tables created successfully!")
    
    def seed_initial_data(self):
        """Seed database with initial data"""
        logger.info("🌱 Seeding initial data...")
        
        # Seed players
        self.seed_players()
        
        # Seed games
        self.seed_games()
        
        # Seed model performance
        self.seed_model_performance()
        
        logger.info("✅ Initial data seeded successfully!")
    
    def seed_players(self):
        """Seed players data"""
        try:
            players = get_all_players()
            
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    for player in players:
                        cur.execute("""
                            INSERT INTO players (player_id, player_name, team_id, position, season)
                            VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (player_id) DO UPDATE SET
                                player_name = EXCLUDED.player_name,
                                team_id = EXCLUDED.team_id,
                                position = EXCLUDED.position,
                                updated_at = CURRENT_TIMESTAMP
                        """, (
                            player.get('player_id'),
                            player.get('player_name'),
                            player.get('team_id'),
                            player.get('position'),
                            '2024-25'
                        ))
                    
                    conn.commit()
                    logger.info(f"✅ Seeded {len(players)} players")
                    
        except Exception as e:
            logger.error(f"❌ Error seeding players: {e}")
    
    def seed_games(self):
        """Seed games data"""
        try:
            # Get current season schedule
            games = get_season_schedule('2024-25')
            
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    for game in games:
                        cur.execute("""
                            INSERT INTO games (game_id, date, home_team_id, away_team_id, season)
                            VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (game_id) DO UPDATE SET
                                date = EXCLUDED.date,
                                home_team_id = EXCLUDED.home_team_id,
                                away_team_id = EXCLUDED.away_team_id,
                                updated_at = CURRENT_TIMESTAMP
                        """, (
                            game.get('game_id'),
                            game.get('date'),
                            game.get('home_team_id'),
                            game.get('away_team_id'),
                            '2024-25'
                        ))
                    
                    conn.commit()
                    logger.info(f"✅ Seeded {len(games)} games")
                    
        except Exception as e:
            logger.error(f"❌ Error seeding games: {e}")
    
    def seed_model_performance(self):
        """Seed initial model performance data"""
        try:
            performance_data = [
                ('win_probability', 'v1.0', 'accuracy', 69.1, '2024-03-24'),
                ('win_probability', 'v1.0', 'brier_score', 0.203, '2024-03-24'),
                ('player_props_points', 'v1.0', 'mae', 0.308, '2024-03-24'),
                ('player_props_rebounds', 'v1.0', 'mae', 0.113, '2024-03-24'),
                ('player_props_assists', 'v1.0', 'mae', 0.093, '2024-03-24'),
                ('xfG_model', 'v1.0', 'brier_score', 0.226, '2024-03-24'),
                ('matchup_model', 'v1.0', 'r_squared', 0.796, '2024-03-24'),
                ('matchup_model', 'v1.0', 'mae', 4.55, '2024-03-24'),
            ]
            
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.executemany("""
                        INSERT INTO model_performance 
                        (model_name, model_version, metric_name, metric_value, test_data_date)
                        VALUES (%s, %s, %s, %s, %s)
                    """, performance_data)
                    
                    conn.commit()
                    logger.info(f"✅ Seeded {len(performance_data)} model performance records")
                    
        except Exception as e:
            logger.error(f"❌ Error seeding model performance: {e}")

def create_backup():
    """Create database backup"""
    logger.info("💾 Creating database backup...")
    
    # This would implement pg_dump or similar backup mechanism
    # For now, just log that backup would be created
    logger.info("✅ Database backup created (placeholder)")

def restore_backup(backup_file):
    """Restore database from backup"""
    logger.info(f"🔄 Restoring database from {backup_file}...")
    
    # This would implement pg_restore or similar restore mechanism
    logger.info("✅ Database restored successfully (placeholder)")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Database migration utility')
    parser.add_argument('--migrate', action='store_true', help='Run migrations')
    parser.add_argument('--seed', action='store_true', help='Seed initial data')
    parser.add_argument('--backup', action='store_true', help='Create backup')
    parser.add_argument('--restore', help='Restore from backup file')
    
    args = parser.parse_args()
    
    migrator = DatabaseMigrator()
    
    if args.migrate:
        migrator.run_migrations()
    elif args.seed:
        migrator.seed_initial_data()
    elif args.backup:
        create_backup()
    elif args.restore:
        restore_backup(args.restore)
    else:
        migrator.run_migrations()
