from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, SmallInteger, Boolean
from sqlalchemy.orm import relationship
from . import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(200), nullable=False)
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    reset_token = Column(String(200), nullable=True)
    reset_token_expiry = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    last_login_at = Column(DateTime, nullable=True, comment="最后一次登录时间")
    access_expires_at = Column(DateTime, nullable=True, comment="账户访问到期时间")
    allowed_competitions = Column(Text, nullable=True, comment="可访问赛事 slug JSON 列表，空表示全部")
    can_access_sporttery = Column(Boolean, default=False, nullable=False, comment="是否可查看体彩购买方案")


class InviteCode(Base):
    __tablename__ = "invite_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(10), unique=True, nullable=False, index=True)
    use_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, autoincrement=True)
    competition_slug = Column(String(40), nullable=False, default="worldcup-2026", index=True)
    name = Column(String(50), nullable=False, index=True)
    name_en = Column(String(50))
    flag_url = Column(String(200))
    rank = Column(Integer, default=0)
    points = Column(Integer, comment="联赛积分")
    played = Column(Integer, comment="已赛场次")
    won = Column(Integer, comment="胜")
    draw = Column(Integer, comment="平")
    lost = Column(Integer, comment="负")
    goals_for = Column(Integer, comment="进球")
    goals_against = Column(Integer, comment="失球")
    attack = Column(Integer, default=0, comment="进攻评分 0-100")
    defend = Column(Integer, default=0, comment="防守评分 0-100")
    midfield = Column(Integer, default=0, comment="中场评分 0-100")
    speed = Column(Integer, default=0, comment="速度评分 0-100")
    physical = Column(Integer, default=0, comment="体能评分 0-100")
    tactic = Column(String(50), comment="战术风格")
    price = Column(String(50), comment="总身价")
    group_name = Column(String(10), comment="小组")
    external_id = Column(Integer, comment="football-data.org 球队 ID")
    season = Column(String(20), comment="赛季 如 2025/26")
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    players = relationship("Player", back_populates="team", lazy="selectin")


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    name = Column(String(50), nullable=False)
    name_en = Column(String(50))
    position = Column(String(20), comment="位置: GK/DF/MF/FW")
    number = Column(Integer)
    age = Column(Integer)
    status = Column(String(20), default="active", comment="active/minor_injury/injured/suspended")
    ability = Column(Integer, default=0, comment="能力值 0-100")
    is_starter = Column(SmallInteger, default=1, comment="是否主力")
    nationality = Column(String(50), comment="国籍")
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    team = relationship("Team", back_populates="players")


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    competition_slug = Column(String(40), nullable=False, default="worldcup-2026", index=True)
    stage = Column(String(30), nullable=False, index=True, comment="小组赛/1/8决赛/1/4决赛/半决赛/季军赛/决赛")
    group_name = Column(String(10), comment="小组名称")
    team_a = Column(String(50), nullable=False)
    team_b = Column(String(50), nullable=False)
    match_time = Column(DateTime, nullable=False, index=True)
    location = Column(String(100))
    stadium = Column(String(100))
    result_a = Column(Integer, nullable=True, default=None)
    result_b = Column(Integer, nullable=True, default=None)
    status = Column(String(20), default="upcoming", comment="upcoming/live/finished")
    season = Column(String(20), comment="赛季 如 2025/26")
    matchday = Column(Integer, comment="联赛轮次")
    external_id = Column(Integer, comment="football-data.org 比赛 ID")
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class Odds(Base):
    __tablename__ = "odds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False, index=True)
    win_win = Column(Float, comment="主胜赔率")
    draw = Column(Float, comment="平局赔率")
    win_lose = Column(Float, comment="客胜赔率")
    handicap = Column(String(20), comment="让球盘口")
    handicap_win = Column(Float, comment="让球主胜赔率")
    handicap_draw = Column(Float, comment="让球平局赔率")
    handicap_lose = Column(Float, comment="让球客胜赔率")
    over_under = Column(String(20), comment="大小球盘口")
    over_odds = Column(Float, comment="大球赔率")
    under_odds = Column(Float, comment="小球赔率")
    score_odds = Column(Text, comment="比分赔率 JSON: {1:0: 6.5, 2:0: 8.0, ...}")
    half_full_odds = Column(Text, comment="半全场赔率 JSON: {胜胜: 3.5, ...}")
    source = Column(String(50), comment="数据来源")
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False, index=True)
    win_rate = Column(Float, comment="胜率百分比")
    draw_rate = Column(Float, comment="平局率百分比")
    lose_rate = Column(Float, comment="负率百分比")
    best_score = Column(Text, comment="预测比分 JSON: [\"2:0\", \"1:0\", \"3:1\"]")
    handicap_result = Column(String(20), comment="让球结果")
    total_goals = Column(String(10), comment="总进球预测")
    reason = Column(Text, comment="预测理由")
    model_used = Column(String(50), comment="使用模型")
    confidence = Column(Float, default=0.8, comment="置信度")
    create_time = Column(DateTime, default=datetime.now)


class CrawlerLog(Base):
    __tablename__ = "crawler_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    crawler_type = Column(String(30), comment="schedule/team/odds")
    status = Column(String(20), comment="success/failed")
    records_count = Column(Integer, default=0)
    error_message = Column(Text)
    start_time = Column(DateTime, default=datetime.now)
    end_time = Column(DateTime)


class HkjcMeetingCache(Base):
    __tablename__ = "hkjc_meeting_cache"

    id = Column(String(32), primary_key=True, comment="赛事日 ID")
    meeting_date = Column(String(10), nullable=False, index=True)
    venue_code = Column(String(8), nullable=False, index=True)
    payload = Column(Text, nullable=False, comment="赛事 JSON")
    source = Column(String(32), default="hkjc_graphql")
    synced_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class HkjcRaceResult(Base):
    __tablename__ = "hkjc_race_results"

    id = Column(String(48), primary_key=True, comment="date-venue-raceNo")
    meeting_date = Column(String(10), nullable=False, index=True)
    venue_code = Column(String(8), nullable=False, index=True)
    race_no = Column(Integer, nullable=False)
    payload = Column(Text, nullable=False, comment="赛果 JSON")
    synced_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
