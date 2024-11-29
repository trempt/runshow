import staticmaps  # type: ignore
import polyline  # type: ignore
import PIL.ImageDraw
from typing import Tuple, Optional, List, Any
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Float

Base = declarative_base()


class Activity(Base):
    __tablename__ = "activities"

    run_id = Column(Integer, primary_key=True)
    distance = Column(Float, nullable=False)
    moving_time = Column(String, nullable=False)
    start_date = Column(String, nullable=False)
    summary_polyline = Column(String, nullable=False)
    average_speed = Column(Float, nullable=False)


def textsize(
    self: PIL.ImageDraw.ImageDraw, *args: Any, **kwargs: Any
) -> Tuple[int, int]:
    x, y, w, h = self.textbbox((0, 0), *args, **kwargs)
    return w, h  # type: ignore


# Monkeypatch fix for https://github.com/flopp/py-staticmaps/issues/39
PIL.ImageDraw.ImageDraw.textsize = textsize  # type: ignore


def format_pace(d: float) -> str:
    if not d:  # Check for NaN
        return "0"
    pace: float = (1000.0 / 60.0) * (1.0 / d)
    minutes: int = int(pace)
    seconds: int = int((pace - minutes) * 60.0)
    return f"{minutes}'{str(seconds).zfill(2)}"


def convert_moving_time_to_sec(moving_time: str) -> int:
    if not moving_time:
        return 0
    # Handle both "2 days, 12:34:56" and "12:34:56" formats
    time_parts = moving_time.split()
    time_str = time_parts[-1].split(".")[0] if len(time_parts) > 1 else moving_time
    hours, minutes, seconds = map(int, time_str.split(":"))
    total_seconds: int = (hours * 60 + minutes) * 60 + seconds
    return total_seconds


def format_run_time(moving_time: str) -> str:
    total_seconds: int = convert_moving_time_to_sec(moving_time)
    seconds: int = total_seconds % 60
    minutes: int = total_seconds // 60
    if minutes == 0:
        return f"{seconds}s"
    return f"{minutes}mins"


class RouteShow:
    def __init__(self, database: Optional[str] = None, is_all: bool = False):
        if not database:
            database = "data/data.db"
        self.engine = create_engine(f"sqlite:///{database}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()
        self.is_all = is_all

    def _get_activities(self) -> List[Activity]:
        if self.is_all:
            return self.session.query(Activity).all()
        return (
            self.session.query(Activity)
            .order_by(Activity.run_id.desc())
            .limit(10)
            .all()
        )

    def generate_routes(self) -> None:
        activities: List[Activity] = self._get_activities()
        for row in activities:
            context = staticmaps.Context()
            lines = polyline.decode(row.summary_polyline)
            line = [staticmaps.create_latlng(p[0], p[1]) for p in lines]
            context.add_object(staticmaps.Line(line))
            svg_image = context.render_svg(600, 600)
            if not row.start_date or not row.distance or not row.moving_time:
                continue
            date_str = row.start_date[:16]
            svg_image.add(
                svg_image.text(
                    date_str,
                    insert=(100, 50),
                    fill="black",
                    font_size="20px",
                    font_weight="bold",
                    text_anchor="middle",
                )
            )
            distance = round(row.distance / 1000, 1)
            duration = format_run_time(str(row.moving_time))
            pace = format_pace(float(row.average_speed or 0))
            texts: List[Tuple[str, int]] = [
                (f"⏱ {duration}", 100),
                (f"{distance} 公里", 300),
                (f"⌚ {pace}", 500),
            ]
            for text, x in texts:
                svg_image.add(
                    svg_image.text(
                        text,
                        insert=(x, 560),
                        fill="black",
                        font_size="30px",
                        font_weight="bold",
                        text_anchor="middle",
                    )
                )
            # filenme like 20241011_5km_30mins
            filename = f"{row.start_date[:10].replace('-', '')}_{distance}km_{duration}"

            with open(f"{filename}.svg", "w", encoding="utf-8") as f:
                svg_image.write(f, pretty=True)