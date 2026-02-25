fn main() {
    let a = 1;
    let b = 2;
    let (a, b) = (b, a);
    println!("{} {}", a, b);
}
