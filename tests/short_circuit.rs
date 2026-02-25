fn main() {
    let x = false && (1 / 0 > 0);
    println!("{}", x);
    let y = true || (1 / 0 > 0);
    println!("{}", y);
}
