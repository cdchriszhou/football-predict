"""HKJC public GraphQL queries (info.cld.hkjc.com)."""

RACE_MEETINGS_QUERY = """
fragment raceFragment on Race {
  id
  no
  status
  raceName_en
  raceName_ch
  postTime
  distance
  go_en
  go_ch
  raceClass_en
  raceClass_ch
  raceTrack { description_en description_ch }
  raceCourse { description_en description_ch displayCode }
}

query raceMeetings($date: String, $venueCode: String) {
  activeMeetings: raceMeetings {
    id
    venueCode
    date
    status
    races { no postTime status }
  }
  raceMeetings(date: $date, venueCode: $venueCode) {
    id
    status
    venueCode
    date
    totalNumberOfRace
    meetingType
    country { namech nameen }
    races {
      ...raceFragment
      runners {
        id
        no
        status
        name_ch
        name_en
        handicapWeight
        currentWeight
        currentRating
        barrierDrawNumber
        last6run
        winOdds
        jockey { code name_en name_ch }
        trainer { code name_en name_ch }
        horse { id code }
      }
    }
  }
}
"""

RACE_ODDS_QUERY = """
query racing($date: String, $venueCode: String, $oddsTypes: [OddsType], $raceNo: Int) {
  raceMeetings(date: $date, venueCode: $venueCode) {
    pmPools(oddsTypes: $oddsTypes, raceNo: $raceNo) {
      oddsType
      lastUpdateTime
      oddsNodes { combString oddsValue hotFavourite }
    }
  }
}
"""
