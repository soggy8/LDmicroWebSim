"""
Parser for LDmicro C code output.
Builds an AST from the token stream.
"""

from dataclasses import dataclass, field
from typing import Union
from .lexer import Token, TokenType, Lexer


# ============================================================================
# AST Node Definitions
# ============================================================================

@dataclass
class ASTNode:
    """Base class for all AST nodes."""
    pass


# --- Expressions ---

@dataclass
class NumberLiteral(ASTNode):
    value: int | float
    raw: str  # Original string representation


@dataclass
class Identifier(ASTNode):
    name: str


@dataclass
class ArrayAccess(ASTNode):
    array: ASTNode
    index: ASTNode


@dataclass
class BinaryOp(ASTNode):
    operator: str
    left: ASTNode
    right: ASTNode


@dataclass
class UnaryOp(ASTNode):
    operator: str
    operand: ASTNode
    prefix: bool = True  # True for prefix (!x), False for postfix (x++)


@dataclass
class Assignment(ASTNode):
    target: ASTNode
    operator: str  # =, +=, -=, etc.
    value: ASTNode


@dataclass
class FunctionCall(ASTNode):
    name: str
    arguments: list[ASTNode]


@dataclass
class TernaryOp(ASTNode):
    condition: ASTNode
    true_expr: ASTNode
    false_expr: ASTNode


# --- Statements ---

@dataclass
class ExpressionStatement(ASTNode):
    expression: ASTNode


@dataclass
class IfStatement(ASTNode):
    condition: ASTNode
    then_body: list[ASTNode]
    else_body: list[ASTNode] | None = None


@dataclass
class WhileStatement(ASTNode):
    condition: ASTNode
    body: list[ASTNode]


@dataclass
class ForStatement(ASTNode):
    init: ASTNode | None
    condition: ASTNode | None
    update: ASTNode | None
    body: list[ASTNode]


@dataclass
class ReturnStatement(ASTNode):
    value: ASTNode | None = None


@dataclass
class Block(ASTNode):
    statements: list[ASTNode]


# --- Declarations ---

@dataclass
class VariableDeclaration(ASTNode):
    type_name: str
    name: str
    is_array: bool = False
    array_size: int | None = None
    initial_value: ASTNode | None = None


@dataclass
class FunctionDeclaration(ASTNode):
    return_type: str
    name: str
    parameters: list[tuple[str, str]]  # (type, name) pairs
    body: list[ASTNode] | None = None  # None for prototypes


@dataclass
class TypedefDeclaration(ASTNode):
    original_type: str
    new_name: str


@dataclass
class StructDeclaration(ASTNode):
    name: str | None
    members: list[VariableDeclaration]


# --- Program ---

@dataclass
class Program(ASTNode):
    declarations: list[ASTNode] = field(default_factory=list)


# ============================================================================
# Parser
# ============================================================================

class ParseError(Exception):
    def __init__(self, message: str, token: Token):
        self.message = message
        self.token = token
        super().__init__(f"Parse error at line {token.line}: {message}")


class Parser:
    """
    Recursive descent parser for LDmicro C code.
    Handles the subset of C that LDmicro generates.
    """
    
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0
    
    @classmethod
    def from_source(cls, source: str) -> 'Parser':
        """Create a parser from source code."""
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        return cls(tokens)
    
    @property
    def current(self) -> Token:
        if self.pos >= len(self.tokens):
            return self.tokens[-1]  # EOF
        return self.tokens[self.pos]
    
    def peek(self, offset: int = 1) -> Token:
        pos = self.pos + offset
        if pos >= len(self.tokens):
            return self.tokens[-1]  # EOF
        return self.tokens[pos]
    
    def advance(self) -> Token:
        token = self.current
        self.pos += 1
        return token
    
    def expect(self, token_type: TokenType, message: str = None) -> Token:
        if self.current.type != token_type:
            msg = message or f"Expected {token_type.name}, got {self.current.type.name}"
            raise ParseError(msg, self.current)
        return self.advance()
    
    def match(self, *token_types: TokenType) -> bool:
        return self.current.type in token_types
    
    def consume_if(self, token_type: TokenType) -> Token | None:
        if self.current.type == token_type:
            return self.advance()
        return None
    
    # ========================================================================
    # Parsing Methods
    # ========================================================================
    
    def parse(self) -> Program:
        """Parse the entire program."""
        program = Program()
        
        while not self.match(TokenType.EOF):
            decl = self.parse_declaration()
            if decl:
                program.declarations.append(decl)
        
        return program
    
    def parse_declaration(self) -> ASTNode | None:
        """Parse a top-level declaration."""
        
        # Typedef
        if self.match(TokenType.TYPEDEF):
            return self.parse_typedef()
        
        # Struct
        if self.match(TokenType.STRUCT):
            return self.parse_struct_declaration()
        
        # Variable or function declaration
        if self.is_type_specifier():
            return self.parse_var_or_func_declaration()
        
        # Skip unknown tokens (preprocessor leftovers, etc.)
        self.advance()
        return None
    
    def is_type_specifier(self) -> bool:
        """Check if current token starts a type specifier."""
        return self.match(
            TokenType.VOID, TokenType.INT, TokenType.CHAR,
            TokenType.SHORT, TokenType.LONG, TokenType.UNSIGNED,
            TokenType.SIGNED, TokenType.STATIC, TokenType.CONST,
            TokenType.SWORD, TokenType.SBYTE, TokenType.STRUCT
        )
    
    def parse_type(self) -> str:
        """Parse a type specifier."""
        parts = []
        
        while self.match(TokenType.STATIC, TokenType.CONST, TokenType.UNSIGNED, TokenType.SIGNED):
            parts.append(self.advance().value)
        
        if self.match(TokenType.STRUCT):
            parts.append(self.advance().value)
            if self.match(TokenType.IDENTIFIER):
                parts.append(self.advance().value)
        elif self.match(TokenType.VOID, TokenType.INT, TokenType.CHAR,
                       TokenType.SHORT, TokenType.LONG, TokenType.SWORD, TokenType.SBYTE):
            parts.append(self.advance().value)
        elif self.match(TokenType.IDENTIFIER):
            # Custom type name
            parts.append(self.advance().value)
        
        # Handle pointers
        while self.match(TokenType.STAR):
            parts.append(self.advance().value)
        
        return ' '.join(parts)
    
    def parse_typedef(self) -> TypedefDeclaration:
        """Parse typedef declaration."""
        self.expect(TokenType.TYPEDEF)
        original_type = self.parse_type()
        
        # The new name can be an identifier OR a type keyword (like SWORD, SBYTE)
        # since this is where those types get defined
        if self.match(TokenType.IDENTIFIER):
            new_name = self.advance().value
        elif self.match(TokenType.SWORD, TokenType.SBYTE):
            new_name = self.advance().value
        else:
            raise ParseError("Expected type name in typedef", self.current)
        
        self.expect(TokenType.SEMICOLON)
        return TypedefDeclaration(original_type, new_name)
    
    def parse_struct_declaration(self) -> StructDeclaration:
        """Parse struct declaration."""
        self.expect(TokenType.STRUCT)
        
        name = None
        if self.match(TokenType.IDENTIFIER):
            name = self.advance().value
        
        members = []
        if self.match(TokenType.LBRACE):
            self.advance()
            while not self.match(TokenType.RBRACE):
                member = self.parse_var_declaration()
                members.append(member)
            self.expect(TokenType.RBRACE)
        
        self.expect(TokenType.SEMICOLON)
        return StructDeclaration(name, members)
    
    def parse_var_or_func_declaration(self) -> ASTNode:
        """Parse variable or function declaration."""
        type_name = self.parse_type()
        name = self.expect(TokenType.IDENTIFIER).value
        
        # Function declaration
        if self.match(TokenType.LPAREN):
            return self.parse_function_declaration(type_name, name)
        
        # Array declaration
        if self.match(TokenType.LBRACKET):
            return self.parse_array_declaration(type_name, name)
        
        # Variable declaration
        initial_value = None
        if self.match(TokenType.ASSIGN):
            self.advance()
            initial_value = self.parse_expression()
        
        self.expect(TokenType.SEMICOLON)
        return VariableDeclaration(type_name, name, False, None, initial_value)
    
    def parse_var_declaration(self) -> VariableDeclaration:
        """Parse a variable declaration (for struct members, etc.)."""
        type_name = self.parse_type()
        name = self.expect(TokenType.IDENTIFIER).value
        
        is_array = False
        array_size = None
        
        if self.match(TokenType.LBRACKET):
            is_array = True
            self.advance()
            if self.match(TokenType.NUMBER):
                array_size = int(self.advance().value)
            self.expect(TokenType.RBRACKET)
        
        self.expect(TokenType.SEMICOLON)
        return VariableDeclaration(type_name, name, is_array, array_size)
    
    def parse_array_declaration(self, type_name: str, name: str) -> VariableDeclaration:
        """Parse array declaration."""
        self.expect(TokenType.LBRACKET)
        
        array_size = None
        if self.match(TokenType.NUMBER):
            array_size = int(self.advance().value)
        
        self.expect(TokenType.RBRACKET)
        
        initial_value = None
        if self.match(TokenType.ASSIGN):
            self.advance()
            initial_value = self.parse_initializer()
        
        self.expect(TokenType.SEMICOLON)
        return VariableDeclaration(type_name, name, True, array_size, initial_value)
    
    def parse_initializer(self) -> ASTNode:
        """Parse array or struct initializer."""
        if self.match(TokenType.LBRACE):
            self.advance()
            values = []
            while not self.match(TokenType.RBRACE):
                values.append(self.parse_expression())
                if not self.match(TokenType.RBRACE):
                    self.expect(TokenType.COMMA)
            self.expect(TokenType.RBRACE)
            # Return as a list wrapped in a node
            return values  # We'll handle this specially
        return self.parse_expression()
    
    def parse_function_declaration(self, return_type: str, name: str) -> FunctionDeclaration:
        """Parse function declaration or definition."""
        self.expect(TokenType.LPAREN)
        
        parameters = []
        while not self.match(TokenType.RPAREN):
            if self.match(TokenType.VOID):
                self.advance()
                break
            
            param_type = self.parse_type()
            param_name = ""
            if self.match(TokenType.IDENTIFIER):
                param_name = self.advance().value
            parameters.append((param_type, param_name))
            
            if not self.match(TokenType.RPAREN):
                self.expect(TokenType.COMMA)
        
        self.expect(TokenType.RPAREN)
        
        # Function prototype
        if self.match(TokenType.SEMICOLON):
            self.advance()
            return FunctionDeclaration(return_type, name, parameters, None)
        
        # Function body
        body = self.parse_block()
        return FunctionDeclaration(return_type, name, parameters, body)
    
    def parse_block(self) -> list[ASTNode]:
        """Parse a block of statements."""
        self.expect(TokenType.LBRACE)
        statements = []
        
        while not self.match(TokenType.RBRACE):
            stmt = self.parse_statement()
            if stmt:
                statements.append(stmt)
        
        self.expect(TokenType.RBRACE)
        return statements
    
    def parse_statement(self) -> ASTNode | None:
        """Parse a statement."""
        
        # Block
        if self.match(TokenType.LBRACE):
            return Block(self.parse_block())
        
        # If statement
        if self.match(TokenType.IF):
            return self.parse_if_statement()
        
        # While loop
        if self.match(TokenType.WHILE):
            return self.parse_while_statement()
        
        # For loop
        if self.match(TokenType.FOR):
            return self.parse_for_statement()
        
        # Return
        if self.match(TokenType.RETURN):
            return self.parse_return_statement()
        
        # Variable declaration
        if self.is_type_specifier():
            return self.parse_var_or_func_declaration()
        
        # Empty statement
        if self.match(TokenType.SEMICOLON):
            self.advance()
            return None
        
        # Expression statement
        return self.parse_expression_statement()
    
    def parse_if_statement(self) -> IfStatement:
        """Parse if/else statement."""
        self.expect(TokenType.IF)
        self.expect(TokenType.LPAREN)
        condition = self.parse_expression()
        self.expect(TokenType.RPAREN)
        
        # Then body
        if self.match(TokenType.LBRACE):
            then_body = self.parse_block()
        else:
            stmt = self.parse_statement()
            then_body = [stmt] if stmt else []
        
        # Else body
        else_body = None
        if self.match(TokenType.ELSE):
            self.advance()
            if self.match(TokenType.LBRACE):
                else_body = self.parse_block()
            else:
                stmt = self.parse_statement()
                else_body = [stmt] if stmt else []
        
        return IfStatement(condition, then_body, else_body)
    
    def parse_while_statement(self) -> WhileStatement:
        """Parse while loop."""
        self.expect(TokenType.WHILE)
        self.expect(TokenType.LPAREN)
        condition = self.parse_expression()
        self.expect(TokenType.RPAREN)
        
        if self.match(TokenType.LBRACE):
            body = self.parse_block()
        else:
            stmt = self.parse_statement()
            body = [stmt] if stmt else []
        
        return WhileStatement(condition, body)
    
    def parse_for_statement(self) -> ForStatement:
        """Parse for loop."""
        self.expect(TokenType.FOR)
        self.expect(TokenType.LPAREN)
        
        # Init
        init = None
        if not self.match(TokenType.SEMICOLON):
            if self.is_type_specifier():
                init = self.parse_var_or_func_declaration()
            else:
                init = self.parse_expression()
                self.expect(TokenType.SEMICOLON)
        else:
            self.advance()
        
        # Condition
        condition = None
        if not self.match(TokenType.SEMICOLON):
            condition = self.parse_expression()
        self.expect(TokenType.SEMICOLON)
        
        # Update
        update = None
        if not self.match(TokenType.RPAREN):
            update = self.parse_expression()
        self.expect(TokenType.RPAREN)
        
        # Body
        if self.match(TokenType.LBRACE):
            body = self.parse_block()
        else:
            stmt = self.parse_statement()
            body = [stmt] if stmt else []
        
        return ForStatement(init, condition, update, body)
    
    def parse_return_statement(self) -> ReturnStatement:
        """Parse return statement."""
        self.expect(TokenType.RETURN)
        
        value = None
        if not self.match(TokenType.SEMICOLON):
            value = self.parse_expression()
        
        self.expect(TokenType.SEMICOLON)
        return ReturnStatement(value)
    
    def parse_expression_statement(self) -> ExpressionStatement:
        """Parse expression statement."""
        expr = self.parse_expression()
        self.expect(TokenType.SEMICOLON)
        return ExpressionStatement(expr)
    
    # ========================================================================
    # Expression Parsing (Precedence Climbing)
    # ========================================================================
    
    def parse_expression(self) -> ASTNode:
        """Parse an expression."""
        return self.parse_assignment()
    
    def parse_assignment(self) -> ASTNode:
        """Parse assignment expression."""
        left = self.parse_ternary()
        
        if self.match(TokenType.ASSIGN, TokenType.PLUS_ASSIGN, 
                     TokenType.MINUS_ASSIGN, TokenType.STAR_ASSIGN,
                     TokenType.SLASH_ASSIGN):
            op = self.advance().value
            right = self.parse_assignment()
            return Assignment(left, op, right)
        
        return left
    
    def parse_ternary(self) -> ASTNode:
        """Parse ternary conditional."""
        condition = self.parse_logical_or()
        
        # Note: We'd need to add ? token support for ternary
        # LDmicro rarely uses ternary, so skipping for now
        
        return condition
    
    def parse_logical_or(self) -> ASTNode:
        """Parse logical OR (||)."""
        left = self.parse_logical_and()
        
        while self.match(TokenType.OR):
            op = self.advance().value
            right = self.parse_logical_and()
            left = BinaryOp(op, left, right)
        
        return left
    
    def parse_logical_and(self) -> ASTNode:
        """Parse logical AND (&&)."""
        left = self.parse_bitwise_or()
        
        while self.match(TokenType.AND):
            op = self.advance().value
            right = self.parse_bitwise_or()
            left = BinaryOp(op, left, right)
        
        return left
    
    def parse_bitwise_or(self) -> ASTNode:
        """Parse bitwise OR (|)."""
        left = self.parse_bitwise_xor()
        
        while self.match(TokenType.PIPE):
            op = self.advance().value
            right = self.parse_bitwise_xor()
            left = BinaryOp(op, left, right)
        
        return left
    
    def parse_bitwise_xor(self) -> ASTNode:
        """Parse bitwise XOR (^)."""
        left = self.parse_bitwise_and()
        
        while self.match(TokenType.CARET):
            op = self.advance().value
            right = self.parse_bitwise_and()
            left = BinaryOp(op, left, right)
        
        return left
    
    def parse_bitwise_and(self) -> ASTNode:
        """Parse bitwise AND (&)."""
        left = self.parse_equality()
        
        while self.match(TokenType.AMPERSAND):
            op = self.advance().value
            right = self.parse_equality()
            left = BinaryOp(op, left, right)
        
        return left
    
    def parse_equality(self) -> ASTNode:
        """Parse equality (== !=)."""
        left = self.parse_comparison()
        
        while self.match(TokenType.EQ, TokenType.NE):
            op = self.advance().value
            right = self.parse_comparison()
            left = BinaryOp(op, left, right)
        
        return left
    
    def parse_comparison(self) -> ASTNode:
        """Parse comparison (< > <= >=)."""
        left = self.parse_shift()
        
        while self.match(TokenType.LT, TokenType.GT, TokenType.LE, TokenType.GE):
            op = self.advance().value
            right = self.parse_shift()
            left = BinaryOp(op, left, right)
        
        return left
    
    def parse_shift(self) -> ASTNode:
        """Parse shift (<< >>)."""
        left = self.parse_additive()
        
        while self.match(TokenType.LSHIFT, TokenType.RSHIFT):
            op = self.advance().value
            right = self.parse_additive()
            left = BinaryOp(op, left, right)
        
        return left
    
    def parse_additive(self) -> ASTNode:
        """Parse addition/subtraction."""
        left = self.parse_multiplicative()
        
        while self.match(TokenType.PLUS, TokenType.MINUS):
            op = self.advance().value
            right = self.parse_multiplicative()
            left = BinaryOp(op, left, right)
        
        return left
    
    def parse_multiplicative(self) -> ASTNode:
        """Parse multiplication/division/modulo."""
        left = self.parse_unary()
        
        while self.match(TokenType.STAR, TokenType.SLASH, TokenType.PERCENT):
            op = self.advance().value
            right = self.parse_unary()
            left = BinaryOp(op, left, right)
        
        return left
    
    def parse_unary(self) -> ASTNode:
        """Parse unary operators."""
        if self.match(TokenType.EXCLAIM, TokenType.TILDE, TokenType.MINUS, TokenType.PLUS):
            op = self.advance().value
            operand = self.parse_unary()
            return UnaryOp(op, operand, prefix=True)
        
        if self.match(TokenType.INCREMENT, TokenType.DECREMENT):
            op = self.advance().value
            operand = self.parse_unary()
            return UnaryOp(op, operand, prefix=True)
        
        return self.parse_postfix()
    
    def parse_postfix(self) -> ASTNode:
        """Parse postfix operators ([], (), ++, --)."""
        left = self.parse_primary()
        
        while True:
            if self.match(TokenType.LBRACKET):
                self.advance()
                index = self.parse_expression()
                self.expect(TokenType.RBRACKET)
                left = ArrayAccess(left, index)
            elif self.match(TokenType.LPAREN):
                # Function call
                self.advance()
                args = []
                while not self.match(TokenType.RPAREN):
                    args.append(self.parse_expression())
                    if not self.match(TokenType.RPAREN):
                        self.expect(TokenType.COMMA)
                self.expect(TokenType.RPAREN)
                if isinstance(left, Identifier):
                    left = FunctionCall(left.name, args)
                else:
                    raise ParseError("Expected function name", self.current)
            elif self.match(TokenType.INCREMENT, TokenType.DECREMENT):
                op = self.advance().value
                left = UnaryOp(op, left, prefix=False)
            elif self.match(TokenType.DOT):
                self.advance()
                member = self.expect(TokenType.IDENTIFIER).value
                left = BinaryOp('.', left, Identifier(member))
            elif self.match(TokenType.ARROW):
                self.advance()
                member = self.expect(TokenType.IDENTIFIER).value
                left = BinaryOp('->', left, Identifier(member))
            else:
                break
        
        return left
    
    def parse_primary(self) -> ASTNode:
        """Parse primary expressions."""
        # Number
        if self.match(TokenType.NUMBER):
            token = self.advance()
            value = token.value
            # Parse the number
            if value.startswith('0x') or value.startswith('0X'):
                num = int(value, 16)
            elif '.' in value:
                num = float(value.rstrip('fFlL'))
            else:
                num = int(value.rstrip('lLuU'))
            return NumberLiteral(num, value)
        
        # Identifier
        if self.match(TokenType.IDENTIFIER):
            return Identifier(self.advance().value)
        
        # Parenthesized expression
        if self.match(TokenType.LPAREN):
            self.advance()
            expr = self.parse_expression()
            self.expect(TokenType.RPAREN)
            return expr
        
        raise ParseError(f"Unexpected token: {self.current.value}", self.current)


def parse(source: str) -> Program:
    """Convenience function to parse source code."""
    parser = Parser.from_source(source)
    return parser.parse()

