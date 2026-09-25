export default function ValidationMessage({ message, closing }) {
  return <p className="check-error appear" data-closing={closing} role="alert">{message}</p>;
}
