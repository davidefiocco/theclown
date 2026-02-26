fn double_if_positive(x: i64) -> Option<i64> {
    if x <= 0 {
        return None;
    }
    Some(x * 2)
}

fn add_doubled(a: i64, b: i64) -> Option<i64> {
    let da = double_if_positive(a)?;
    let db = double_if_positive(b)?;
    Some(da + db)
}

fn main() {
    println!("{}", add_doubled(3, 4).unwrap());
    println!("{}", add_doubled(-1, 4).is_none());
    println!("{}", add_doubled(3, -2).is_none());
}
