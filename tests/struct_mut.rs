struct Counter {
    value: i64,
}

impl Counter {
    fn new() -> Counter {
        Counter { value: 0 }
    }
}

fn main() {
    let mut c = Counter::new();
    println!("{}", c.value);
    c.value = 42;
    println!("{}", c.value);
}
