enum Direction {
    North,
    South,
    East,
    West,
}

fn describe(d: Direction) -> &'static str {
    match d {
        Direction::North => "up",
        Direction::South => "down",
        Direction::East => "right",
        Direction::West => "left",
    }
}

fn main() {
    println!("{}", describe(Direction::North));
    println!("{}", describe(Direction::West));
}
