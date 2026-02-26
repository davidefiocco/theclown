fn main() {
    let x: Option<i64> = None;
    let v = x.unwrap();
    println!("{}", v);
}
