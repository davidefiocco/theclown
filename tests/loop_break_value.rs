fn main() {
    let x = loop {
        break 42;
    };
    println!("{}", x);
}
