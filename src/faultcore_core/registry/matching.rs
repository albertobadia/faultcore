#[derive(Clone, Debug, Hash, PartialEq, Eq)]
pub enum MatchCondition {
    Key { key: String, value: String },
    Prefix { key: String, prefix: String },
}

#[derive(Clone, Debug)]
pub struct MatchingRule {
    pub conditions: Vec<MatchCondition>,
    pub policy_name: String,
    pub priority: i32,
}
