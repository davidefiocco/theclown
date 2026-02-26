fn main() {
    let a = Some(42);
    let b: Option<i64> = None;

    println!("{}", a.unwrap());
    println!("{}", a.is_some());
    println!("{}", a.is_none());
    println!("{}", b.is_some());
    println!("{}", b.is_none());
    println!("{}", b.unwrap_or(99));
}
