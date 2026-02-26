struct Data {
    value: i64,
}

fn main() {
    let a = Data { value: 10 };
    let b = a;
    println!("{}", b.value);
    println!("{}", a.value);
}
