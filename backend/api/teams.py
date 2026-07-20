from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_db
from db.models import Team, Player
from utils.response import success, paginate
from api.auth import get_current_user
from api.competitions import resolve_competition
from api.deps import require_competition_entitlement
from data.competitions import get_competition
from data.status_constants import normalize_player_status
from data.match_status import season_label_for
from data.league_standings import ensure_league_standings_stats

router = APIRouter(dependencies=[Depends(require_competition_entitlement)])


def _team_standing_row(t: Team) -> dict:
    gf, ga = t.goals_for, t.goals_against
    gd = (gf - ga) if gf is not None and ga is not None else None
    return {
        "id": t.id,
        "rank": t.rank,
        "name": t.name,
        "name_en": t.name_en,
        "flag_url": t.flag_url,
        "season": t.season,
        "points": t.points,
        "played": t.played,
        "won": t.won,
        "draw": t.draw,
        "lost": t.lost,
        "goals_for": gf,
        "goals_against": ga,
        "goal_diff": gd,
    }


@router.get("/standings")
async def get_team_standings(
    competition: str = Query("worldcup-2026"),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """League table for club competitions (current season)."""
    comp_slug = resolve_competition(competition)
    comp = get_competition(comp_slug)
    if not comp or comp.get("type") != "club":
        return success([])

    season = season_label_for(comp)
    await ensure_league_standings_stats(db, comp_slug)

    filters = [Team.competition_slug == comp_slug, Team.rank > 0]
    if season:
        season_rows = (await db.execute(
            select(Team).where(*filters, Team.season == season, Team.played > 0)
            .order_by(Team.rank.asc())
        )).scalars().all()
        teams = season_rows if season_rows else (await db.execute(
            select(Team).where(*filters, Team.played > 0).order_by(Team.rank.asc())
        )).scalars().all()
    else:
        teams = (await db.execute(
            select(Team).where(*filters).order_by(Team.rank.asc())
        )).scalars().all()

    return success([_team_standing_row(t) for t in teams])


@router.get("/list")
async def get_teams(
    competition: str = Query("worldcup-2026", description="赛事 slug"),
    sort: str = Query("rank", description="排序字段: rank/attack/defend"),
    order: str = Query("asc", description="排序方向: asc/desc"),
    group_name: str = Query(None, description="小组筛选"),
    search: str = Query(None, description="队名搜索"),
    page: int = Query(1, ge=1),
    size: int = Query(48, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    comp_slug = resolve_competition(competition)
    query = select(Team).where(Team.competition_slug == comp_slug)
    count_query = select(func.count(Team.id)).where(Team.competition_slug == comp_slug)

    if group_name:
        query = query.where(Team.group_name == group_name)
        count_query = count_query.where(Team.group_name == group_name)
    if search:
        query = query.where(Team.name.like(f"%{search}%"))
        count_query = count_query.where(Team.name.like(f"%{search}%"))

    sort_col = getattr(Team, sort, Team.rank)
    if order == "desc":
        query = query.order_by(sort_col.desc())
    else:
        query = query.order_by(sort_col.asc())

    total = (await db.execute(count_query)).scalar()
    teams = (await db.execute(query.offset((page - 1) * size).limit(size))).scalars().all()

    data = [
        {
            "id": t.id, "competition_slug": t.competition_slug,
            "name": t.name, "name_en": t.name_en, "flag_url": t.flag_url,
            "rank": t.rank, "attack": t.attack, "defend": t.defend,
            "midfield": t.midfield, "speed": t.speed, "physical": t.physical,
            "tactic": t.tactic, "price": t.price, "group_name": t.group_name,
            "season": t.season,
            "overall": round((t.attack + t.defend + t.midfield) / 3, 1)
        }
        for t in teams
    ]
    return success(paginate(data, total, page, size))


@router.get("/groups")
async def get_teams_by_group(
    competition: str = Query("worldcup-2026"),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    comp_slug = resolve_competition(competition)
    teams = (await db.execute(
        select(Team).where(Team.competition_slug == comp_slug)
        .order_by(Team.group_name.asc(), Team.rank.asc())
    )).scalars().all()

    groups = {}
    for t in teams:
        g = t.group_name or "未分组"
        if g not in groups:
            groups[g] = []
        groups[g].append({
            "id": t.id, "name": t.name, "name_en": t.name_en, "flag_url": t.flag_url,
            "rank": t.rank, "attack": t.attack, "defend": t.defend,
            "midfield": t.midfield, "tactic": t.tactic, "price": t.price
        })

    return success(groups)


@router.get("/{team_id}")
async def get_team_detail(
    team_id: int,
    competition: str = Query(None, description="校验所属赛事 slug"),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    team = (await db.execute(select(Team).where(Team.id == team_id))).scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="球队不存在")
    if competition:
        comp_slug = resolve_competition(competition)
        if team.competition_slug != comp_slug:
            raise HTTPException(status_code=404, detail="球队不属于当前赛事")

    players = (await db.execute(
        select(Player).where(Player.team_id == team_id).order_by(Player.ability.desc())
    )).scalars().all()

    return success({
        "id": team.id, "competition_slug": team.competition_slug,
        "name": team.name, "name_en": team.name_en, "flag_url": team.flag_url,
        "rank": team.rank,
        "attack": team.attack, "defend": team.defend, "midfield": team.midfield,
        "speed": team.speed, "physical": team.physical,
        "tactic": team.tactic, "price": team.price, "group_name": team.group_name,
        "season": team.season,
        "players": [
            {
                "id": p.id, "name": p.name, "name_en": p.name_en,
                "position": p.position, "number": p.number, "age": p.age,
                "nationality": p.nationality,
                "status": normalize_player_status(p.status), "ability": p.ability, "is_starter": p.is_starter
            }
            for p in players
        ]
    })
