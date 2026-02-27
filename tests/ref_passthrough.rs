struct Counter {
    value: i64,
}
fn increment(c: &mut Counter) {
    c.value += 1;
}
fn main() {
    let mut c = Counter { value: 0 };
    increment(&mut c);
    increment(&mut c);
    println!("{}", c.value);
}
