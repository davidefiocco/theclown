fn add(a: i32, b: i32) -> i32 {
    a + b
}

fn double(x: i32) -> i32 {
    x * 2
}

fn main() {
    let sum = add(3, 4);
    let dbl = double(5);
    println!("{}", sum);
    println!("{}", dbl);
}
